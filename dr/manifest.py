"""Generation manifest build and validation (schema version 1)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1


class ManifestError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemberRecord:
    path: str  # archive-relative POSIX path
    bytes: int
    sha256: str


@dataclass
class Manifest:
    manifest_version: int
    generation_id: str
    created_utc: str
    source_host_label: str
    repo_shas: dict[str, str]
    deployed_identities: dict[str, Any]
    participants: list[dict[str, Any]]
    archive_format: str
    zstd_level: int
    recommissioned_dependencies: list[str]
    verification: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Manifest":
        raw = json.loads(text)
        expected = {
            "manifest_version",
            "generation_id",
            "created_utc",
            "source_host_label",
            "repo_shas",
            "deployed_identities",
            "participants",
            "archive_format",
            "zstd_level",
            "recommissioned_dependencies",
            "verification",
        }
        missing = expected - set(raw)
        if missing:
            raise ManifestError(f"manifest missing fields: {sorted(missing)}")
        if raw["manifest_version"] != MANIFEST_VERSION:
            raise ManifestError(f"unsupported manifest version: {raw['manifest_version']}")
        return cls(**{k: raw[k] for k in expected})


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest_member_index(
    manifest: Manifest,
    *,
    member_index: dict[str, tuple[int, str]],
    manifest_present: bool,
) -> None:
    """Fail-closed member check against an in-memory path -> (bytes, sha256) index.

    Used by both extracted-tree validation and stream validation so the
    archive never needs a second full uncompressed copy on disk.
    """
    if manifest.manifest_version != MANIFEST_VERSION:
        raise ManifestError("unsupported manifest version")
    from .config import safe_path
    ids = [p.get("id") for p in manifest.participants]
    if not ids or len(ids) != len(set(ids)) or any(not safe_path(i) or "/" in i for i in ids):
        raise ManifestError("invalid participant set")
    recorded: dict[str, MemberRecord] = {}
    for participant in manifest.participants:
        if participant.get("status") != "captured":
            raise ManifestError(f"participant {participant.get('id')!r} was not fully captured")
        if not participant.get("members"):
            raise ManifestError("participant has no members")
        for member_raw in participant.get("members", []):
            record = MemberRecord(
                path=member_raw["path"], bytes=member_raw["bytes"], sha256=member_raw["sha256"]
            )
            if not safe_path(record.path) or not record.path.startswith(participant["id"] + "/"):
                raise ManifestError("member outside participant namespace")
            if record.path in recorded:
                raise ManifestError(f"duplicate manifest member: {record.path}")
            recorded[record.path] = record
    if not recorded:
        raise ManifestError("manifest records no payload members")
    if not manifest_present:
        raise ManifestError("extracted archive is missing manifest.json")
    for rel_path, record in sorted(recorded.items()):
        actual = member_index.get(rel_path)
        if actual is None:
            raise ManifestError(f"manifest member missing or not a regular file: {rel_path}")
        actual_size, actual_hash = actual
        if actual_size != record.bytes:
            raise ManifestError(
                f"member size mismatch for {rel_path}: manifest={record.bytes} actual={actual_size}"
            )
        if actual_hash != record.sha256:
            raise ManifestError(f"member hash mismatch for {rel_path}")
    allowed = set(recorded) | {MANIFEST_NAME}
    extras = set(member_index) - allowed
    if extras:
        raise ManifestError(f"archive contains members not recorded in manifest: {sorted(extras)[:5]}")


def validate_manifest_members(manifest: Manifest, extract_root: Path) -> None:
    """Verify every recorded member exists under extract_root and hashes match.

    Also verifies no unexpected files are present: the payload must be exactly
    the allowlisted manifest plus recorded members (fail closed on extras, so a
    corrupted or contaminated archive is never restored).
    """
    member_index: dict[str, tuple[int, str]] = {}
    manifest_present = False
    for path in extract_root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        rel = str(path.relative_to(extract_root)).replace("\\", "/")
        if rel == MANIFEST_NAME:
            manifest_present = True
            continue
        member_index[rel] = (path.stat().st_size, sha256_file(path))
    validate_manifest_member_index(
        manifest, member_index=member_index, manifest_present=manifest_present
    )
