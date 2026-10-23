"""Offline regression and fault tests. No network, production files or credentials."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from dr import runner
from dr.archive import validate_archive, build_archive
from dr.capture import validate_file
from dr.config import load, ProtonConfig
from dr.manifest import Manifest, validate_manifest_member_index
from dr.monitor import check
from dr.proton import ProtonTransportError, parse_list_output
from dr.retention import parse_generation_name, select_retention
from dr.state import read, write, locked, Busy

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2030, 7, 20, 12, tzinfo=timezone.utc)


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        subprocess.run([str(ROOT / 'scripts/make-demo-config'), str(self.work)], check=True,
                       stdout=subprocess.DEVNULL)
        self.config = load(self.work / 'config.json')
        self.root = Path(self.config['root'])
        self.remote = self.work / 'remote'
        self.time = patch('dr.runner.utcnow', return_value=NOW)
        self.time.start()

    def tearDown(self):
        self.time.stop()
        self.temp.cleanup()

    def mode(self, value):
        self.config['proton']['env']['FAKE_MODE'] = value

    def events(self):
        path = self.remote / 'events.jsonl'
        return [json.loads(line)['command'] for line in path.read_text().splitlines()] if path.exists() else []

    def seed_history(self):
        self.root.mkdir(exist_ok=True)
        self.remote.mkdir(exist_ok=True)
        verified = {}
        for i in range(1, 41):
            stamp = (NOW - timedelta(days=i)).strftime('%Y%m%dT%H%M%SZ')
            name = f'reference-dr-{stamp}-{i:08x}.tar.zst'
            (self.remote / name).write_bytes(b'fixture historical object')
            verified[name] = {'remote_dir': self.config['proton']['remote_dir'], 'bytes': 25, 'sha256': '0'*64}
        write(self.root / 'status.json', {'last_verified': (NOW-timedelta(days=1)).isoformat(),
                                        'failures': 0, 'verified': verified})

    def test_end_to_end_capture_upload_listing_and_separate_restore(self):
        result = runner.run(self.config)
        self.assertTrue(result['verified'])
        events = self.events()
        self.assertEqual(events[:3], ['upload', 'list', 'list'])
        status = read(self.root / 'status.json')
        name = next(iter(status['verified']))
        restored = runner.verify(self.config, name)
        self.assertTrue(restored['trusted_archive_hash_matched'])
        self.assertEqual(read(self.root / 'status.json')['last_verified'], status['last_verified'])
        self.assertEqual(len(status['verified']), 1)
        self.assertFalse(list(self.root.glob('capture-*')))
        self.assertFalse(list(self.root.glob('restore-*')))

    def assert_failed_without_prune(self, mode):
        self.seed_history()
        before = read(self.root / 'status.json')['last_verified']
        self.mode(mode)
        with self.assertRaises(ProtonTransportError):
            runner.run(self.config)
        status = read(self.root / 'status.json')
        self.assertEqual(status['last_verified'], before)
        self.assertEqual(status['failures'], 1)
        self.assertNotIn('trash', self.events())
        self.assertEqual(len(list(self.remote.glob('*.tar.zst'))), 40 + (mode != 'upload-failure'))

    def test_missing_size_fails_closed_and_no_prune(self):
        self.assert_failed_without_prune('missing-size')

    def test_upload_failure_fails_closed_and_no_prune(self):
        self.assert_failed_without_prune('upload-failure')
        self.assertNotIn('list', self.events())

    def test_wrong_size_fails_closed_and_no_prune(self):
        self.assert_failed_without_prune('wrong-size')

    def test_missing_participant_prevents_upload(self):
        self.config['participants'][-1]['argv'] = ['/usr/bin/true', '{output_dir}']
        with self.assertRaises(ValueError):
            runner.run(self.config)
        self.assertEqual(self.events(), [])
        self.assertNotIn('last_verified', read(self.root / 'status.json'))

    def test_failed_capture_command_prevents_upload(self):
        self.config['participants'][0]['argv'] = ['/usr/bin/false', '{output_dir}']
        with self.assertRaises(ValueError):
            runner.run(self.config)
        self.assertEqual(self.events(), [])

    def test_corrupt_archive_before_upload_gates_everything(self):
        original = runner.build_archive
        def corrupt(**kwargs):
            original(**kwargs)
            kwargs['output_path'].write_bytes(b'corrupt archive')
        with patch('dr.runner.build_archive', side_effect=corrupt):
            with self.assertRaises(Exception):
                runner.run(self.config)
        self.assertEqual(self.events(), [])
        self.assertNotIn('last_verified', read(self.root / 'status.json'))

    def test_download_corruption_fails_restore(self):
        runner.run(self.config)
        name = next(iter(read(self.root / 'status.json')['verified']))
        (self.remote / name).write_bytes(b'corrupt remote fixture')
        with self.assertRaises(ValueError):
            runner.verify(self.config, name)
        self.assertFalse((self.root / 'last-restore-check.json').exists())

    def test_manifest_missing_required_participant_gates_upload(self):
        original = runner.capture
        def omit(config, staging):
            parts = original(config, staging)
            # Remove both files and manifest entry to avoid relying on incidental extra-file detection.
            import shutil
            shutil.rmtree(staging / 'auth')
            return parts[:-1]
        with patch('dr.runner.capture', side_effect=omit):
            with self.assertRaises(ValueError):
                runner.run(self.config)
        self.assertEqual(self.events(), [])

    def test_retention_runs_only_after_verification_and_is_bounded(self):
        self.seed_history()
        unrelated = self.remote / 'unrelated.tar.zst'
        unrelated.write_bytes(b'invented unrelated object')
        unreceipted = self.remote / 'reference-dr-20290101T000000Z-aaaaaaaa.tar.zst'
        unreceipted.write_bytes(b'unverified')
        result = runner.run(self.config)
        self.assertLessEqual(result['retention']['kept'], 9)
        events = self.events()
        self.assertGreater(events.index('trash'), events.index('list'))
        self.assertLessEqual(len(read(self.root / 'status.json')['verified']), 9)
        self.assertTrue(unrelated.exists())
        self.assertTrue(unreceipted.exists())

    def test_no_prune_on_duplicate_listing(self):
        self.seed_history()
        tx = runner.transport(self.config)
        objs = tx.list_remote()
        with patch.object(tx, 'list_remote', return_value=objs + objs[:1]):
            with self.assertRaises(ValueError):
                runner.prune(self.config, tx, 'invalid', NOW)
        self.assertNotIn('trash', self.events())

    def test_stale_backup_alert_independent_of_run_lock_and_throttled(self):
        self.root.mkdir()
        write(self.root / 'status.json', {'last_verified': (NOW-timedelta(hours=49)).isoformat()})
        sent = []
        with locked(self.root / 'run.lock', blocking=False):
            result = check(self.config, now=NOW, notifier=lambda c, label: sent.append(label))
        self.assertEqual(result, {'condition': 'stale_backup', 'notified': True})
        self.assertEqual(check(self.config, now=NOW, notifier=lambda *a: self.fail())['notified'], False)
        self.assertEqual(sent, ['stale_backup'])

    def test_persistent_failure_gating_healthy_silence_and_no_success(self):
        self.root.mkdir()
        sent = []
        notify = lambda c, label: sent.append(label)
        self.assertEqual(check(self.config, now=NOW, notifier=notify)['condition'], 'no_verified_backup')
        status = {'last_verified': NOW.isoformat(), 'failures': 1}
        write(self.root / 'status.json', status)
        self.assertIsNone(check(self.config, now=NOW, notifier=notify)['condition'])
        status['failures'] = 2
        write(self.root / 'status.json', status)
        self.assertEqual(check(self.config, now=NOW, notifier=notify)['condition'], 'persistent_failure')

    def test_alert_delivery_failure_does_not_acknowledge(self):
        self.root.mkdir()
        with self.assertRaises(OSError):
            check(self.config, now=NOW, notifier=lambda *a: (_ for _ in ()).throw(OSError()))
        self.assertFalse((self.root / 'alerts.json').exists())

    def test_lock_prevents_overlap_without_failure_increment(self):
        self.root.mkdir()
        with locked(self.root / 'run.lock', blocking=False):
            with self.assertRaises(Busy):
                runner.run(self.config)
        self.assertFalse((self.root / 'status.json').exists())

    def test_binary_checksum_mismatch_prevents_capture(self):
        self.config['binary_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            runner.run(self.config)
        self.assertEqual(self.events(), [])

    def test_cli_does_not_log_sensitive_subprocess_error(self):
        self.mode('upload-failure')
        config_path = self.work / 'config.json'
        config_path.write_text(json.dumps(self.config))
        result = subprocess.run([str(ROOT/'scripts/dr'), '--config', str(config_path), 'run'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('sensitive-error-sentinel', result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stderr)['error_class'], 'ProtonTransportError')

    def test_listing_accepts_production_json_shapes_and_rejects_ambiguous_size(self):
        objects = parse_list_output('{"items":[{"name":{"ok":true,"value":"demo"},"activeRevision":{"claimedSize":12}}]}')
        self.assertEqual((objects[0].name, objects[0].size), ('demo', 12))
        with self.assertRaises(ProtonTransportError):
            parse_list_output('not json')

    def test_archive_rejects_traversal_links_duplicates_and_unrecorded_files(self):
        for kind in ('traversal', 'link', 'duplicate', 'extra'):
            raw = self.work / (kind + '.tar')
            with tarfile.open(raw, 'w') as tar:
                info = tarfile.TarInfo('../escape' if kind == 'traversal' else 'extra')
                info.size = 1
                if kind == 'link':
                    info.type = tarfile.SYMTYPE
                    info.linkname = '/tmp/escape'
                    info.size = 0
                tar.addfile(info, io.BytesIO(b'x'))
                if kind == 'duplicate':
                    tar.addfile(info, io.BytesIO(b'x'))
            compressed = raw.with_suffix('.zst')
            subprocess.run(['/usr/bin/zstd', '-q', '-f', str(raw), '-o', str(compressed)], check=True)
            with self.assertRaises(Exception):
                validate_archive(archive_path=compressed, work_root=self.work/'validate', zstd_binary='/usr/bin/zstd')
        self.assertFalse((self.work.parent / 'escape').exists())

    def test_retention_future_timestamp_refuses_pruning(self):
        gen = parse_generation_name('reference-dr-20310101T000000Z-aaaaaaaa.tar.zst', 'reference-dr')
        with self.assertRaises(Exception):
            select_retention([gen], now=NOW)

    def test_bad_sqlite_rejected(self):
        path = self.work / 'bad.sqlite3'
        path.write_text('invented invalid database')
        with self.assertRaises(Exception):
            validate_file(path, 'sqlite')


if __name__ == '__main__':
    unittest.main()
