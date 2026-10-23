"""Atomic receipts and short status lock, independent of long capture lock."""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import json
import os
import tempfile


class Busy(RuntimeError):
    pass


@contextmanager
def locked(path, blocking=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise Busy('another operation holds the lock') from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read(path):
    path = Path(path)
    if not path.exists():
        return {'failures': 0, 'verified': {}}
    return json.loads(path.read_text())


def write(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.receipt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def update(root, mutate):
    root = Path(root)
    with locked(root / 'status.lock'):
        status = read(root / 'status.json')
        mutate(status)
        write(root / 'status.json', status)
