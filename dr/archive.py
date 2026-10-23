"""tar + zstd generation archive creation and local validation.

One archive per generation: an uncompressed POSIX tar stream of the staging
payload (manifest + captured members) compressed once with zstd. Local
validation is mandatory before upload: the archive must be listable, contain
the manifest, contain every manifest member with matching hashes and sizes,
contain no unrecorded members, and contain no forbidden reconstructable trees.

Working-set rule: never materialize an uncompressed tar sidecar, and never
extract a second full payload copy merely to validate. Stream tar through
zstd, and hash members from the decompress stream. Full extract remains only
for restore rehearsal, which needs files on disk.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tarfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .manifest import MANIFEST_NAME, Manifest, ManifestError, validate_manifest_member_index


class ArchiveError(RuntimeError):
    pass


_HASH_CHUNK = 1 << 20


def _close_quietly(stream: object | None) -> None:
    if stream is None:
        return
    try:
        if getattr(stream, "closed", False):
            return
        stream.close()
    except Exception:
        pass


def _reap_process(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=30)
        except Exception:
            pass
    _close_quietly(proc.stdin)
    _close_quietly(proc.stdout)
    _close_quietly(proc.stderr)


def _start_stderr_drain(proc: subprocess.Popen) -> tuple[list[bytes], threading.Thread]:
    chunks: list[bytes] = []

    def _drain() -> None:
        try:
            if proc.stderr is not None:
                chunks.append(proc.stderr.read() or b"")
        except Exception:
            chunks.append(b"")

    thread = threading.Thread(target=_drain, daemon=True)
    thread.start()
    return chunks, thread


def _stderr_text(chunks: list[bytes], thread: threading.Thread) -> str:
    thread.join(timeout=30)
    return (chunks[0] if chunks else b"").decode("utf-8", "replace").strip()[:200]


def _run_zstd(zstd_binary: str, argv: list[str], timeout_s: int = 3600) -> None:
    """Legacy file-to-file zstd helper retained for tests that still patch it."""
    try:
        result = subprocess.run(
            [zstd_binary, *argv],
            capture_output=True,
            timeout=timeout_s,
        )
    except FileNotFoundError as exc:
        raise ArchiveError(f"zstd binary missing: {zstd_binary}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ArchiveError("zstd timed out") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()[:200]
        raise ArchiveError(f"zstd failed ({result.returncode}): {detail}")


@contextmanager
def open_zstd_writer(zstd_binary: str, zstd_level: int, output_path: Path) -> Iterator[object]:
    """Yield a binary file object that zstd-compresses to output_path.

    The compressor reads stdin. Callers write an uncompressed tar stream into
    the yielded handle. A sibling `.partial` is replaced onto output_path only
    after zstd exits 0 with a non-empty file. Any non-success path unlinks the
    partial and reaps the child.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(output_path.name + ".partial")
    partial.unlink(missing_ok=True)
    try:
        proc = subprocess.Popen(
            [zstd_binary, f"-{zstd_level}", "-T0", "-f", "-o", str(partial)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ArchiveError(f"zstd binary missing: {zstd_binary}") from exc
    if proc.stdin is None:
        _reap_process(proc)
        raise ArchiveError("zstd stdin pipe was not created")
    writer_error: BaseException | None = None
    succeeded = False
    stderr_chunks, stderr_thread = _start_stderr_drain(proc)
    try:
        try:
            yield proc.stdin
        except BaseException as exc:
            writer_error = exc
        try:
            _close_quietly(proc.stdin)
            proc.stdin = None  # type: ignore[assignment]
            rc = proc.wait(timeout=3600)
        except subprocess.TimeoutExpired as exc:
            raise ArchiveError("zstd timed out") from exc
        except OSError as exc:
            if writer_error is None:
                writer_error = exc
            rc = proc.poll()
            if rc is None:
                raise ArchiveError("zstd wait failed") from exc
        detail = _stderr_text(stderr_chunks, stderr_thread)
        if rc != 0:
            raise ArchiveError(f"zstd failed ({rc}): {detail}") from writer_error
        if writer_error is not None:
            raise writer_error
        if not partial.is_file() or partial.stat().st_size == 0:
            raise ArchiveError("archive creation produced no output")
        os.replace(partial, output_path)
        succeeded = True
    finally:
        _reap_process(proc)
        if not succeeded:
            partial.unlink(missing_ok=True)


@contextmanager
def open_zstd_reader(zstd_binary: str, archive_path: Path) -> Iterator[object]:
    """Yield a binary file object that streams decompressed archive bytes."""
    try:
        proc = subprocess.Popen(
            [zstd_binary, "-d", "-T0", "-c", str(archive_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ArchiveError(f"zstd binary missing: {zstd_binary}") from exc
    if proc.stdout is None:
        _reap_process(proc)
        raise ArchiveError("zstd stdout pipe was not created")
    reader_error: BaseException | None = None
    stderr_chunks, stderr_thread = _start_stderr_drain(proc)
    try:
        try:
            yield proc.stdout
        except BaseException as exc:
            reader_error = exc
        try:
            _close_quietly(proc.stdout)
            proc.stdout = None  # type: ignore[assignment]
            rc = proc.wait(timeout=3600)
        except subprocess.TimeoutExpired as exc:
            raise ArchiveError("zstd timed out") from exc
        except OSError as exc:
            if reader_error is None:
                reader_error = exc
            rc = proc.poll()
            if rc is None:
                raise ArchiveError("zstd wait failed") from exc
        if reader_error is not None:
            raise reader_error
        if rc != 0:
            detail = _stderr_text(stderr_chunks, stderr_thread)
            raise ArchiveError(f"zstd failed ({rc}): {detail}")
        _stderr_text(stderr_chunks, stderr_thread)
    finally:
        _reap_process(proc)


def _add_staging_to_tar(staging_root: Path, tar: tarfile.TarFile) -> None:
    for entry in sorted(staging_root.rglob("*")):
        arcname = entry.relative_to(staging_root).as_posix()
        if entry.is_symlink():
            raise ArchiveError(f"refusing to archive symlink: {arcname}")
        tar.add(entry, arcname=arcname, recursive=False, filter=lambda info: info)


def build_archive(
    *,
    staging_root: Path,
    output_path: Path,
    zstd_binary: str,
    zstd_level: int,
) -> None:
    """Create output_path (tar.zst) from the full contents of staging_root.

    Streams tar directly into zstd. Does not write an uncompressed `.tar.tmp`.
    """
    if not staging_root.is_dir():
        raise ArchiveError(f"staging root missing: {staging_root}")
    if not (staging_root / MANIFEST_NAME).is_file():
        raise ArchiveError("staging root has no manifest.json")
    with open_zstd_writer(zstd_binary, zstd_level, output_path) as sink:
        with tarfile.open(fileobj=sink, mode="w|", format=tarfile.PAX_FORMAT) as tar:
            _add_staging_to_tar(staging_root, tar)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise ArchiveError("archive creation produced no output")


def _reject_unsafe_tar_member(member: tarfile.TarInfo) -> None:
    if member.issym() or member.islnk():
        raise ArchiveError(f"archive contains link member: {member.name}")
    from .config import safe_path
    if not safe_path(member.name.rstrip("/") if member.isdir() else member.name):
        raise ArchiveError(f"archive member escapes extract root: {member.name}")


def extract_archive(
    *,
    archive_path: Path,
    extract_root: Path,
    zstd_binary: str,
) -> None:
    """Decompress and extract archive_path into extract_root (created if needed).

    Streams zstd stdout into tarfile. Does not write an uncompressed tar sidecar.
    """
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ArchiveError(f"archive missing: {archive_path}")
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        with open_zstd_reader(zstd_binary, archive_path) as raw:
            with tarfile.open(fileobj=raw, mode="r|") as tar:
                for member in tar:
                    _reject_unsafe_tar_member(member)
                    tar.extract(member, path=extract_root, filter="data")
    except tarfile.TarError as exc:
        raise ArchiveError(f"archive is not a readable tar: {exc}") from exc


def _member_name(member: tarfile.TarInfo) -> str:
    """Use the tar member name as extract would see it.

    Do not character-strip leading '.' or '/': a member stored as
    `.finance/finance.sqlite3` must not satisfy a manifest path of
    `finance/finance.sqlite3`.
    """
    return member.name


def validate_archive(
    *,
    archive_path: Path,
    work_root: Path,
    zstd_binary: str,
) -> Manifest:
    """Full local validation. Returns the parsed manifest on success.

    Hashes every regular-file member from the decompress stream. Does not
    extract a second payload tree. `work_root` is accepted for API compatibility
    and is created, but is not used as an extract destination.
    """
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ArchiveError(f"archive missing: {archive_path}")
    work_root.mkdir(parents=True, exist_ok=True)
    member_index: dict[str, tuple[int, str]] = {}
    total_bytes = 0
    seen_names = set()
    manifest: Manifest | None = None
    try:
        with open_zstd_reader(zstd_binary, archive_path) as raw:
            with tarfile.open(fileobj=raw, mode="r|") as tar:
                for member in tar:
                    _reject_unsafe_tar_member(member)
                    if member.name in seen_names:
                        raise ArchiveError("duplicate archive member")
                    seen_names.add(member.name)
                    total_bytes += member.size
                    if total_bytes > 20 * (1 << 30) or len(seen_names) > 100000:
                        raise ArchiveError("archive exceeds reference validation bounds")
                    if member.isdir():
                        continue
                    if not member.isfile():
                        raise ArchiveError(f"unsupported archive member type: {member.name}")
                    handle = tar.extractfile(member)
                    if handle is None:
                        raise ArchiveError(f"archive member unreadable: {member.name}")
                    name = _member_name(member)
                    if name == MANIFEST_NAME:
                        if manifest is not None or member.size > (1 << 20):
                            raise ArchiveError("duplicate or oversized manifest")
                        data = handle.read()
                        try:
                            manifest = Manifest.from_json(data.decode("utf-8"))
                        except ManifestError:
                            raise
                        except (ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
                            raise ManifestError(f"manifest is not valid: {exc}") from exc
                        continue
                    if name in member_index:
                        raise ArchiveError("duplicate archive member")
                    digest = hashlib.sha256()
                    size = 0
                    while True:
                        chunk = handle.read(_HASH_CHUNK)
                        if not chunk:
                            break
                        digest.update(chunk)
                        size += len(chunk)
                    member_index[name] = (size, digest.hexdigest())
    except tarfile.TarError as exc:
        raise ArchiveError(f"archive is not a readable tar: {exc}") from exc
    if manifest is None:
        raise ArchiveError("archive does not contain manifest.json")
    validate_manifest_member_index(
        manifest, member_index=member_index, manifest_present=True
    )
    return manifest


def validate_archive_against_staging(archive_path: Path, staging_root: Path) -> None:
    if not archive_path.is_file() or archive_path.stat().st_size == 0:
        raise ArchiveError("archive missing or empty before upload")
    if not (staging_root / MANIFEST_NAME).is_file():
        raise ArchiveError("staging manifest missing before upload")
    for suffix in (".tar.tmp", ".partial"):
        sidecar = archive_path.with_name(archive_path.name + suffix)
        if sidecar.exists():
            raise ArchiveError("uncompressed tar sidecar was left beside the archive")
