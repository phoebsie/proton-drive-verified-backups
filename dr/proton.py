"""Proton Drive CLI transport adapter for the DR reference.

Executes the official Proton Drive CLI via strict argv templates from DR config
(no shell, no credentials in argv, no secret material in logs). A run is only
transport-verified after an independent remote listing confirms the uploaded
object at the expected path with the expected size; the upload exit code alone
is never success.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import ProtonConfig


class ProtonTransportError(RuntimeError):
    pass


_PLACEHOLDERS = {
    "{binary}": "binary",
    "{remote_dir}": "remote_dir",
    "{local_path}": "local_path",
    "{local_dir}": "local_dir",
    "{remote_path}": "remote_path",
    "{remote_name}": "remote_name",
}


@dataclass(frozen=True)
class RemoteObject:
    name: str
    size: int | None
    raw: dict | None = None


class ProtonTransport:
    def __init__(
        self,
        config: ProtonConfig,
        *,
        extra_env: dict[str, str] | None = None,
        archive_prefix: str | None = None,
    ) -> None:
        self._config = config
        self._extra_env = dict(extra_env or {})
        self._archive_prefix = archive_prefix

    def _argv(self, command: str, **values: str) -> list[str]:
        template = self._config.commands.get(command)
        if template is None:
            raise ProtonTransportError(f"no proton command template for {command!r}")
        values.setdefault("binary", self._config.binary)
        values.setdefault("remote_dir", self._config.remote_dir)
        argv: list[str] = []
        for token in template:
            for placeholder, key in _PLACEHOLDERS.items():
                if placeholder in token:
                    if key not in values or not values[key]:
                        raise ProtonTransportError(f"proton {command}: missing value for {placeholder}")
                    token = token.replace(placeholder, values[key])
            argv.append(token)
        return argv

    def _run(self, argv: list[str], *, timeout_s: int | None = None) -> subprocess.CompletedProcess[bytes]:
        binary = Path(self._config.binary)
        if argv[0] != str(binary):
            raise ProtonTransportError("proton argv[0] must equal the configured binary")
        if binary.is_symlink() or not binary.is_file():
            raise ProtonTransportError(f"proton binary missing or symlink: {binary}")
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": "/root",
            "LANG": "C.UTF-8",
        }
        env.update(self._config.env)
        env.update(self._extra_env)
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                timeout=timeout_s or self._config.command_timeout_s,
                env=env,
            )
        except FileNotFoundError as exc:
            raise ProtonTransportError(f"cannot execute proton binary: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProtonTransportError(f"proton {argv[1:3]} timed out") from exc

    # -- high-level operations -------------------------------------------------

    def list_remote(self, remote_dir: str | None = None) -> list[RemoteObject]:
        argv = self._argv("list", remote_dir=remote_dir) if remote_dir else self._argv("list")
        result = self._run(argv)
        if result.returncode != 0:
            raise ProtonTransportError(f"proton list failed ({result.returncode})")
        return parse_list_output(result.stdout.decode("utf-8", "replace"))

    def upload(self, local_path: Path, object_name: str) -> None:
        if object_name != local_path.name:
            raise ProtonTransportError("upload object name must equal the local file name")
        _validate_object_name(object_name, self._archive_prefix)
        argv = self._argv("upload", local_path=str(local_path))
        result = self._run(argv)
        if result.returncode != 0:
            raise ProtonTransportError(f"proton upload failed ({result.returncode})")

    def download(self, object_name: str, local_dir: Path) -> Path:
        _validate_object_name(object_name, self._archive_prefix)
        local_dir = Path(local_dir)
        argv = self._argv(
            "download",
            remote_path=f"{self._config.remote_dir}/{object_name}",
            local_dir=str(local_dir),
        )
        result = self._run(argv)
        if result.returncode != 0:
            raise ProtonTransportError(f"proton download failed ({result.returncode})")
        downloaded = local_dir / object_name
        if not downloaded.is_file():
            raise ProtonTransportError("proton download reported success but object is absent locally")
        return downloaded

    def delete_remote(self, object_name: str) -> None:
        """Remove a remote object from the live namespace: trash it.

        The CLI permanently deletes only from within /trash and permanent
        deletion requires the trash-internal path, so retention pruning moves
        objects to trash; Proton's trash retention completes the purge.
        A blanket empty-trash is deliberately never used (it would touch
        non-DR trashed material).
        """
        _validate_object_name(object_name, self._archive_prefix)
        remote_path = f"{self._config.remote_dir}/{object_name}"
        trash_argv = self._argv("trash", remote_path=remote_path)
        result = self._run(trash_argv)
        if result.returncode != 0:
            raise ProtonTransportError(f"proton trash failed ({result.returncode})")

    # -- verification ----------------------------------------------------------

    def verify_remote_object(self, object_name: str, expected_size: int) -> RemoteObject:
        """Independent presence/metadata check in the remote namespace.

        Fail closed: an object whose size the CLI cannot report is NOT
        verified evidence, because the work order requires expected-size
        agreement, not bare presence.
        """
        matches = [obj for obj in self.list_remote() if obj.name == object_name]
        if len(matches) != 1:
            raise ProtonTransportError("expected exactly one remote object")
        for remote in matches:
            if remote.name == object_name:
                if remote.size is None:
                    raise ProtonTransportError("remote listing did not report size; presence alone is insufficient")
                if remote.size != expected_size:
                    raise ProtonTransportError(
                        f"remote object size mismatch for {object_name}: "
                        f"remote={remote.size} expected={expected_size}"
                    )
                return remote
        raise ProtonTransportError(f"remote object not found in {self._config.remote_dir!r}: {object_name}")


def _validate_object_name(name: str, archive_prefix: str | None = None) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or name in {".", ".."}:
        raise ProtonTransportError(f"invalid remote object name: {name!r}")
    if archive_prefix is not None:
        from .retention import parse_generation_name

        if parse_generation_name(name, archive_prefix) is None:
            raise ProtonTransportError("remote object name does not match the generation pattern")


def parse_list_output(text: str) -> list[RemoteObject]:
    """Parse `filesystem list --json` output defensively.

    The official CLI is documented to emit JSON with --json; accept either a
    top-level list or an object wrapping a list, with tolerant key names. Any
    other shape is a transport failure (fail closed) rather than a blind pass.
    """
    text = text.strip()
    if not text:
        raise ProtonTransportError("proton list produced no output")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtonTransportError(f"proton list output is not JSON: {exc}") from exc
    if isinstance(payload, dict):
        for key in ("items", "entries", "files", "children", "contents", "objects"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            raise ProtonTransportError("proton list JSON has no recognised item list")
    if not isinstance(payload, list):
        raise ProtonTransportError("proton list JSON is not a list")
    objects: list[RemoteObject] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = _entry_name(item)
        if not name:
            continue
        name = name.rstrip("/")
        size_raw = item.get(
            "size",
            item.get(
                "bytes",
                item.get("contentSize", item.get("fileSize", item.get("activeSize"))),
            ),
        )
        if size_raw is None and isinstance(item.get("activeRevision"), dict):
            revision = item["activeRevision"]
            size_raw = revision.get(
                "size",
                revision.get(
                    "claimedSize",
                    revision.get("contentSize", revision.get("fileSize", revision.get("storageSize"))),
                ),
            )
        if size_raw is None:
            size_raw = item.get("totalStorageSize")
        # JSON booleans/floats are not byte counts. int(12.9) must never
        # turn malformed metadata into a matching expected size.
        size: int | None = None
        if type(size_raw) is int and size_raw >= 0:
            size = size_raw
        elif isinstance(size_raw, str) and re.fullmatch(r"[0-9]+", size_raw):
            size = int(size_raw)
        objects.append(RemoteObject(name=name, size=size, raw=item))
    return objects


def _entry_name(item: dict) -> str | None:
    """Extract a node name from a list entry.

    The official CLI emits `"name": {"ok": true, "value": "<name>"}` for
    encrypted-name nodes and plain strings for root sections; accept both.
    A name with ok=false (undecryptable/conflicting) is skipped, not guessed.
    """
    for key in ("name", "filename", "path", "objectName"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            if value.get("ok") is False:
                return None
            inner = value.get("value")
            if isinstance(inner, str) and inner:
                return inner
    return None


def redact(text: str) -> str:
    """Best-effort secret redaction for any CLI/transport output that reaches logs."""
    patterns = (
        re.compile(r"(?i)\b(password|passphrase|token|secret)\b[\"']?\s*[:=]\s*\S+"),
        re.compile(r"(?i)\bauthorization\b[\"']?\s*[:=]\s*\S+(\s+\S+)?"),
        re.compile(r"-----[A-Z ]*PRIVATE KEY-----"),
    )
    for pattern in patterns:
        text = pattern.sub("[redacted]", text)
    return text


