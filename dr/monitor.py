"""Independent 48-hour dead-man and persistent-failure checks; no agent dependency."""
from datetime import datetime, timezone
from pathlib import Path
import json
import ssl
import urllib.request
from .state import locked, read, write


def condition(status, now):
    if not isinstance(status, dict):
        return 'unreadable_status'
    failures = status.get('failures', 0)
    retention = status.get('retention', {})
    if type(failures) is not int or failures < 0 or not isinstance(retention, dict):
        return 'unreadable_status'
    stamp = status.get('last_verified')
    if stamp is None:
        return 'no_verified_backup'
    try:
        last = datetime.fromisoformat(stamp)
        age = (now - last).total_seconds()
    except (ValueError, TypeError):
        return 'invalid_success_time'
    if age < -300:
        return 'future_success_time'
    if age > 48 * 3600:
        return 'stale_backup'
    if failures >= 2:
        return 'persistent_failure'
    if retention.get('error'):
        return 'retention_failure'
    return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(config, label):
    # Notification credentials never enter config, argv, logs, or alert text.
    path = Path(config['notify_file'])
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError('notification file must be private')
    settings = json.loads(path.read_text())
    url = settings['url']
    if not url.startswith('https://'):
        raise ValueError('notification endpoint requires HTTPS')
    headers = {'Title': 'DR backup needs attention', 'Content-Type': 'text/plain'}
    if settings.get('token'):
        headers['Authorization'] = 'Bearer ' + settings['token']
    request = urllib.request.Request(url, data=('DR condition: ' + label).encode(),
                                     headers=headers, method='POST')
    opener = urllib.request.build_opener(NoRedirect(),
                 urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(request, timeout=15) as response:
        if not 200 <= response.status < 300:
            raise ValueError('notification delivery failed')


def check(config, now=None, notifier=send):
    now = now or datetime.now(timezone.utc)
    root = Path(config['root'])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Never waits for the long run.lock. Hung captures cannot suppress the dead-man.
    with locked(root / 'monitor.lock'):
        try:
            label = condition(read(root / 'status.json'), now)
        except (ValueError, TypeError, KeyError, OSError):
            label = 'unreadable_status'
        try:
            alerts = read(root / 'alerts.json')
        except (ValueError, OSError):
            alerts = {}
        if not isinstance(alerts, dict):
            alerts = {}
        if label is None:
            write(root / 'alerts.json', {})
            return {'condition': None, 'notified': False}
        previous = alerts.get('last_utc')
        if previous and alerts.get('condition') == label:
            try:
                elapsed = (now - datetime.fromisoformat(previous)).total_seconds()
            except (ValueError, TypeError):
                elapsed = -1  # Corrupt bookkeeping never suppresses delivery.
            if 0 <= elapsed < 24 * 3600:
                return {'condition': label, 'notified': False, 'suppressed': True}
        notifier(config, label)
        write(root / 'alerts.json', {'condition': label, 'last_utc': now.isoformat()})
        return {'condition': label, 'notified': True}
