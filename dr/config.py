"""Non-secret trusted configuration. No production defaults."""
from dataclasses import dataclass
from pathlib import Path
import json
import re


@dataclass(frozen=True)
class ProtonConfig:
    binary: str
    remote_dir: str
    commands: dict
    env: dict
    command_timeout_s: int = 3600


def load(path):
    config = json.loads(Path(path).read_text())
    if config.get('schema_version') != 1:
        raise ValueError('unsupported config version')
    if not Path(config['root']).is_absolute():
        raise ValueError('root must be absolute')
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,48}', config['archive_prefix']):
        raise ValueError('invalid archive prefix')
    ids = [p['id'] for p in config['participants']]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('missing or duplicate participant')
    for p in config['participants']:
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,48}', p['id']):
            raise ValueError('invalid participant ID')
        files = p['files']
        if not files:
            raise ValueError('participant has no allowlist')
        for name, validator in files.items():
            if not safe_path(name) or validator not in ('file', 'sqlite', 'zip', 'json'):
                raise ValueError('invalid allowlist entry')
        argv = p['argv']
        if not argv or not Path(argv[0]).is_absolute() or '{output_dir}' not in argv:
            raise ValueError('capture requires absolute executable and output directory token')
    proton = config['proton']
    if not Path(proton['binary']).is_absolute() or not proton['remote_dir'].startswith('/my-files/'):
        raise ValueError('invalid Proton binary or destination')
    if not re.fullmatch(r'[0-9a-f]{64}', config['binary_sha256']):
        raise ValueError('set the verified installed binary SHA-256')
    if not Path(proton['env']['HOME']).is_absolute():
        raise ValueError('explicit service HOME required')
    return config


def safe_path(name):
    return (isinstance(name, str) and bool(name) and '\\' not in name
            and not name.startswith('/') and all(p not in ('', '.', '..') for p in name.split('/')))
