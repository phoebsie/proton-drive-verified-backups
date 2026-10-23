from pathlib import Path
from unittest.mock import patch
import importlib.machinery
import importlib.util
import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
from dr.capture import validate_file
from dr.export import export_bank
from dr.policy import check_member
from dr.monitor import condition
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]


class Adapters(unittest.TestCase):
    def test_sqlite_online_backup_includes_wal_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.sqlite3'
            output = root / 'output'
            output.mkdir()
            with sqlite3.connect(source) as conn:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('CREATE TABLE fixture (value TEXT)')
                conn.execute("INSERT INTO fixture VALUES ('invented WAL row')")
                conn.commit()
                subprocess.run([str(ROOT/'scripts/sqlite-capture'), '--source', str(source), str(output)], check=True)
                with sqlite3.connect(output/'state.sqlite3') as restored:
                    self.assertEqual(restored.execute('SELECT value FROM fixture').fetchone()[0], 'invented WAL row')

    def test_hindsight_export_success_and_unsafe_download_rejection(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('document.json', '{"synthetic":true}')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'bank-export.zip'
            responses = iter([(202, b'{"operation_id":"fixture-operation"}'),
                (200, b'{"status":"completed","result_metadata":{"download_url":"/v1/default/files/download/fixture"}}'),
                (200, payload.getvalue())])
            calls = []
            def request(method, path):
                calls.append((method, path))
                return next(responses)
            export_bank('http://127.0.0.1:9999', 'example-bank', output, request=request)
            validate_file(output, 'zip')
            self.assertIn('include_observations=true&include_knowledge_base=true', calls[0][1])
            bad = iter([(202, b'{"operation_id":"fixture"}'),
                (200, b'{"status":"completed","result_metadata":{"download_url":"https://evil.example.invalid/leak"}}')])
            with self.assertRaises(ValueError):
                export_bank('http://127.0.0.1:9999', 'example-bank', output,
                            request=lambda *a: next(bad))

    def test_zip_path_policy_and_unresolved_sidecars(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.zip'
            for name in ('.ssh/id_ed25519', 'browser-profile/Cookies', 'state.sqlite-wal', '../escape'):
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr(name, 'invented')
                with self.assertRaises(ValueError):
                    validate_file(path, 'zip')

    def test_future_success_and_corrupt_time_are_actionable(self):
        now = datetime(2030, 7, 1, tzinfo=timezone.utc)
        self.assertEqual(condition({'last_verified': (now+timedelta(days=1)).isoformat()}, now), 'future_success_time')
        self.assertEqual(condition({'last_verified': 'invalid'}, now), 'invalid_success_time')

    def test_gpg_helper_checks_policy_and_keeps_phrase_on_stdin(self):
        # Test the executable itself with mocked subprocesses and isolated invented input.
        loader = importlib.machinery.SourceFileLoader('preset_fixture', str(ROOT/'scripts/preset-gpg'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            phrase = root/'phrase'
            phrase.write_text('invented-test-passphrase\n')
            phrase.chmod(0o600)
            (root/'gpg-agent.conf').write_text('allow-preset-passphrase\ndefault-cache-ttl 172800\nmax-cache-ttl 172800\n')
            config = root/'config.json'
            config.write_text(json.dumps({'home': str(root), 'gnupghome': str(root),
                'passphrase_file': str(phrase), 'keygrips': ['a'*40],
                'preset_binary': '/usr/lib/gnupg/gpg-preset-passphrase', 'pass_entry': 'synthetic-session'}))
            calls = []
            def run(argv, **kwargs):
                self.assertNotIn('invented-test-passphrase', str(argv) + str(kwargs.get('env')))
                if '--preset' in argv:
                    self.assertEqual(kwargs['stdin'].read(), b'invented-test-passphrase\n')
                calls.append(argv)
            with patch.object(module.sys, 'argv', ['preset-gpg', str(config)]), patch.object(module.subprocess, 'run', side_effect=run):
                module.main()
            self.assertEqual(len(calls), 3)
            (root/'gpg-agent.conf').write_text('allow-preset-passphrase\nmax-cache-ttl 0\n')
            with patch.object(module.sys, 'argv', ['preset-gpg', str(config)]):
                with self.assertRaises(ValueError):
                    module.main()
