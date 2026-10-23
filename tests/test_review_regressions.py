"""Regressions for independent review findings, using invented state only."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import json
import subprocess
import tempfile
import unittest
from dr.config import load
from dr.monitor import check
from dr.proton import parse_list_output, ProtonTransportError, RemoteObject
from dr.runner import run, verify
from dr.state import write, read

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2030, 8, 1, tzinfo=timezone.utc)


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        subprocess.run([str(ROOT/'scripts/make-demo-config'), str(self.work)],
                       check=True, stdout=subprocess.DEVNULL)
        self.config = load(self.work/'config.json')
        self.root = Path(self.config['root'])
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_malformed_status_shapes_always_alert(self):
        malformed = [[], None, 'invalid', {'last_verified': NOW.isoformat(), 'retention': None},
                     {'last_verified': NOW.isoformat(), 'failures': '2'},
                     {'last_verified': NOW.isoformat(), 'failures': -1},
                     {'last_verified': NOW.isoformat(), 'failures': True}]
        for status in malformed:
            with self.subTest(status=status):
                write(self.root/'status.json', status)
                (self.root/'alerts.json').unlink(missing_ok=True)
                calls = []
                result = check(self.config, now=NOW, notifier=lambda c, label: calls.append(label))
                self.assertTrue(result['notified'])
                self.assertTrue(calls)

    def test_malformed_alert_bookkeeping_never_suppresses_delivery(self):
        write(self.root/'status.json', {'last_verified': (NOW-timedelta(hours=49)).isoformat()})
        for alerts in [[], None, {'condition':'stale_backup', 'last_utc':'invalid'},
                       {'condition':'stale_backup', 'last_utc':'2030-08-01T00:00:00'},
                       {'condition':'stale_backup', 'last_utc':123}]:
            with self.subTest(alerts=alerts):
                write(self.root/'alerts.json', alerts)
                calls=[]
                self.assertTrue(check(self.config, now=NOW, notifier=lambda c, label: calls.append(label))['notified'])
                self.assertEqual(calls,['stale_backup'])

    def test_fractional_boolean_negative_and_nondecimal_sizes_are_not_byte_counts(self):
        for size in [12.9, 12.0, True, False, -1, '12.0', '1e3', '-1', ' 12']:
            with self.subTest(size=size):
                value=parse_list_output(json.dumps([{'name':'fixture', 'size':size}]))[0]
                self.assertIsNone(value.size)
        for size in [12,'12']:
            self.assertEqual(parse_list_output(json.dumps([{'name':'fixture','size':size}]))[0].size,12)

    def test_fractional_size_full_pipeline_cannot_advance_freshness_or_prune(self):
        from dr.proton import ProtonTransport
        original = ProtonTransport.list_remote
        def fractional(tx, *args, **kwargs):
            objects = original(tx, *args, **kwargs)
            return parse_list_output(json.dumps([{'name':obj.name, 'size':obj.size+0.9} for obj in objects]))
        with patch.object(ProtonTransport,'list_remote',fractional):
            with self.assertRaises(ProtonTransportError):
                run(self.config)
        status=read(self.root/'status.json')
        self.assertNotIn('last_verified',status)
        self.assertEqual(status['failures'],1)
        events=(self.work/'remote/events.jsonl').read_text()
        self.assertNotIn('trash',events)

    def test_capture_contract_mismatch_blocks_restore(self):
        run(self.config)
        status=read(self.root/'status.json')
        name=next(iter(status['verified']))
        self.config['participants'][0]['contract']='incompatible-v999'
        with self.assertRaisesRegex(ValueError,'contract'):
            verify(self.config,name)
