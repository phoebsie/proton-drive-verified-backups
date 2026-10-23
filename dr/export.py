"""Generic Hindsight document-transfer export, derived from the production adapter.

No memory admission, quality, personalisation, or orchestration implementation.
The API contract is the production 0.10.x shape; other versions need validation.
"""
import json
import re
import time
import urllib.request
from urllib.parse import quote, urlsplit
from .monitor import NoRedirect


def export_bank(base_url, bank, destination, timeout=600, request=None):
    parsed = urlsplit(base_url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.query or parsed.fragment or parsed.path:
        raise ValueError('reference exporter requires a loopback HTTP endpoint')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', bank):
        raise ValueError('invalid bank')
    deadline = time.monotonic() + timeout
    if request is None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        def request(method, path):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('bank export deadline')
            req = urllib.request.Request(base_url + path, method=method)
            with opener.open(req, timeout=min(remaining, 300)) as response:
                data = response.read(20 * (1 << 30) + 1)
                if len(data) > 20 * (1 << 30):
                    raise ValueError('export too large')
                return response.status, data
    prefix = f'/v1/default/banks/{bank}'
    status, raw = request('POST', prefix + '/document-transfer/export?include_observations=true&include_knowledge_base=true')
    operation = json.loads(raw).get('operation_id')
    if status != 202 or not isinstance(operation, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', operation):
        raise ValueError('export operation not accepted')
    while time.monotonic() < deadline:
        _, raw = request('GET', prefix + '/operations/' + operation)
        result = json.loads(raw)
        if result.get('status') == 'completed':
            download = result.get('result_metadata', {}).get('download_url', '')
            if not re.fullmatch(r'/v1/default/files/download/[A-Za-z0-9_/-]+', download) or '..' in download:
                raise ValueError('unsafe export download path')
            status, payload = request('GET', download)
            if status != 200:
                raise ValueError('export download failed')
            destination.write_bytes(payload)
            from .capture import validate_file
            validate_file(destination, 'zip')
            return
        if result.get('status') in ('failed', 'cancelled'):
            raise ValueError('bank export failed')
        time.sleep(min(2, max(0, deadline-time.monotonic())))
    raise TimeoutError('bank export deadline')
