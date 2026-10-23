"""Production-derived capture -> manifest -> archive -> upload -> list -> receipt -> retention."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import secrets
import tempfile
from .archive import build_archive, validate_archive, extract_archive
from .capture import capture, validate_payload
from .config import ProtonConfig
from .manifest import Manifest, MANIFEST_NAME, sha256_file
from .proton import ProtonTransport
from .retention import parse_generation_name, select_retention
from .state import locked, read, write, update


def utcnow():
    return datetime.now(timezone.utc)


def transport(config):
    binary = Path(config['proton']['binary'])
    if binary.is_symlink() or sha256_file(binary) != config['binary_sha256']:
        raise ValueError('CLI binary checksum mismatch or symlink')
    return ProtonTransport(ProtonConfig(**config['proton']), archive_prefix=config['archive_prefix'])


def validate(config, archive, work, expected_id=None):
    manifest = validate_archive(archive_path=archive, work_root=work,
                                zstd_binary=config.get('zstd_binary', '/usr/bin/zstd'))
    if expected_id is not None and manifest.generation_id != expected_id:
        raise ValueError('manifest generation does not match requested object')
    payload = work / 'payload'
    extract_archive(archive_path=archive, extract_root=payload,
                    zstd_binary=config.get('zstd_binary', '/usr/bin/zstd'))
    validate_payload(config, manifest, payload)
    return manifest


def prune(config, tx, current_id, now):
    root = Path(config['root'])
    ledger = read(root / 'status.json').get('verified', {})
    objects = tx.list_remote()
    if len({obj.name for obj in objects}) != len(objects):
        raise ValueError('ambiguous listing; refusing retention')
    # Only locally receipted verified generations of this exact prefix/destination.
    generations = []
    for obj in objects:
        gen = parse_generation_name(obj.name, config['archive_prefix'])
        receipt = ledger.get(obj.name)
        if (gen and receipt and receipt['remote_dir'] == config['proton']['remote_dir']
                and receipt['bytes'] == obj.size):
            generations.append(gen)
    keep, expired = select_retention(generations, now=now)
    if current_id not in keep:
        raise ValueError('current generation not retained; refusing prune')
    deleted = []
    for gen in generations:
        if gen.generation_id in expired:
            tx.delete_remote(gen.name)  # trash only: never empty account trash
            deleted.append(gen.name)
            update(root, lambda status, name=gen.name: status['verified'].pop(name, None))
    return {'kept': len(keep), 'trashed': len(deleted)}


def run(config):
    os.umask(0o077)
    root = Path(config['root'])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with locked(root / 'run.lock', blocking=False):
        try:
            tx = transport(config)
            now = utcnow()
            generation = now.strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(4)
            name = f"{config['archive_prefix']}-{generation}.tar.zst"
            with tempfile.TemporaryDirectory(prefix='capture-', dir=root) as temp:
                work = Path(temp)
                staging = work / 'staging'
                staging.mkdir()
                participants = capture(config, staging)
                manifest = Manifest(1, generation, now.isoformat(), 'backup-controller', {}, {},
                                    participants, 'tar.zst', 3,
                                    config.get('recommissioned_dependencies', []),
                                    {'local_archive_validated': False, 'remote_object_verified': False})
                (staging / MANIFEST_NAME).write_text(manifest.to_json())
                archive = work / name
                build_archive(staging_root=staging, output_path=archive,
                              zstd_binary=config.get('zstd_binary', '/usr/bin/zstd'), zstd_level=3)
                validate(config, archive, work / 'local-check', generation)
                size, digest = archive.stat().st_size, sha256_file(archive)
                tx.upload(archive, name)
                tx.verify_remote_object(name, size)
                verified_at = utcnow().isoformat()
                def success(status):
                    status.update(last_verified=verified_at, failures=0, last_failure=None)
                    status.setdefault('verified', {})[name] = {
                        'bytes': size, 'sha256': digest, 'remote_dir': config['proton']['remote_dir'],
                        'verified_at': verified_at}
                update(root, success)
                try:
                    retention = prune(config, tx, generation, utcnow())
                except Exception:
                    retention = {'error': 'retention incomplete; verified backup remains valid'}
                update(root, lambda status: status.update(retention=retention))
                return {'verified': True, 'generation': generation, 'retention': retention}
        except Exception as exc:
            def failure(status):
                status['failures'] = status.get('failures', 0) + 1
                status['last_failure'] = {'utc': utcnow().isoformat(), 'class': type(exc).__name__}
            update(root, failure)
            raise


def verify(config, name, expected_sha256=None):
    """Separate download + member hashes + SQLite/ZIP proof; never advances freshness."""
    os.umask(0o077)
    gen = parse_generation_name(name, config['archive_prefix'])
    if gen is None:
        raise ValueError('invalid generation name')
    root = Path(config['root'])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with locked(root / 'run.lock', blocking=False):
        tx = transport(config)
        with tempfile.TemporaryDirectory(prefix='restore-', dir=root) as temp:
            work = Path(temp)
            downloaded = tx.download(name, work)
            digest = sha256_file(downloaded)
            receipt = read(root / 'status.json').get('verified', {}).get(name)
            trusted_hash = expected_sha256 or (receipt or {}).get('sha256')
            if trusted_hash and digest != trusted_hash:
                raise ValueError('download hash differs from trusted receipt')
            validate(config, downloaded, work / 'check', gen.generation_id)
            result = {'verified': True, 'generation': gen.generation_id,
                      'sha256': digest, 'trusted_archive_hash_matched': bool(trusted_hash)}
            write(root / 'last-restore-check.json', result)
            return result
