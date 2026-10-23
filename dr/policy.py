"""Small explicit credential-path exclusion, never a content-secrecy guarantee."""
from pathlib import PurePosixPath
from .config import safe_path

FORBIDDEN = {'.ssh', '.gnupg', '.password-store', 'gpg-passphrase', 'private-keys-v1.d',
             'auth-session', 'id_rsa', 'id_ed25519', 'id_ecdsa', 'id_dsa', 'authorized_keys',
             'browser-profile'}


def check_member(name):
    if not safe_path(name):
        raise ValueError('unsafe member path')
    if FORBIDDEN.intersection(PurePosixPath(name).parts):
        raise ValueError('excluded host credential or browser identity')
