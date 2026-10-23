"""Capture every participant through a supported snapshot/export command."""
from pathlib import Path
import json
import os
import sqlite3
import stat
import subprocess
import tempfile
import zipfile
from .config import safe_path
from .manifest import sha256_file
from .policy import check_member


def validate_file(path, kind):
    check_member(path.name)
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise ValueError('missing, empty or unsafe participant file')
    if kind == 'sqlite':
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as conn:
            rows = conn.execute('PRAGMA integrity_check').fetchall()
            if rows != [('ok',)]:
                raise ValueError('SQLite integrity check failed')
    elif kind == 'json':
        json.loads(path.read_text())
    elif kind == 'zip':
        with zipfile.ZipFile(path) as archive:
            names = set()
            expanded = 0
            for member in archive.infolist():
                name = member.filename.rstrip('/') if member.is_dir() else member.filename
                mode = member.external_attr >> 16
                if not safe_path(name) or member.filename in names or stat.S_ISLNK(mode):
                    raise ValueError('unsafe ZIP member')
                check_member(name)
                expanded += member.file_size
                if expanded > 20 * (1 << 30) or len(names) >= 100000:
                    raise ValueError("ZIP exceeds reference validation bounds")
                if name.lower().endswith(("-wal", "-shm", "-journal")):
                    raise ValueError("unresolved database sidecar in ZIP")
                names.add(member.filename)
            if not names or archive.testzip() is not None:
                raise ValueError('ZIP integrity check failed')


def capture(config, staging):
    participants = []
    for entry in config['participants']:
        output = staging / entry['id']
        output.mkdir(mode=0o700)
        argv = [str(output) if token == '{output_dir}' else token for token in entry['argv']]
        result = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
                                     **config.get('capture_env', {})},
                                timeout=entry.get('timeout_s', 1800), shell=False)
        if result.returncode:
            raise ValueError('participant capture command failed')
        actual = set()
        for path in output.rglob('*'):
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise ValueError('capture contains link or special file')
            check_member(path.relative_to(output).as_posix())
            actual.add(path.relative_to(output).as_posix())
        if actual != set(entry['files']):
            raise ValueError('participant file set differs from allowlist')
        records = []
        for name, kind in entry['files'].items():
            path = output / name
            validate_file(path, kind)
            records.append({'path': path.relative_to(staging).as_posix(),
                            'bytes': path.stat().st_size, 'sha256': sha256_file(path)})
        participants.append({'id': entry['id'], 'status': 'captured', 'members': records,
                             'capture_contract': entry.get('contract', 'command-v1')})
    return participants


def validate_payload(config, manifest, root):
    expected = {p['id']: p for p in config['participants']}
    ids = [p['id'] for p in manifest.participants]
    if set(ids) != set(expected) or len(ids) != len(expected):
        raise ValueError('generation missing or duplicates a required participant')
    for part in manifest.participants:
        entry = expected[part['id']]
        if part.get('capture_contract') != entry.get('contract', 'command-v1'):
            raise ValueError('generation capture contract is incompatible')
        paths = {f"{entry['id']}/{name}" for name in entry['files']}
        if part['status'] != 'captured' or {r['path'] for r in part['members']} != paths:
            raise ValueError('generation participant contract mismatch')
        for name, kind in entry['files'].items():
            validate_file(root / entry['id'] / name, kind)
