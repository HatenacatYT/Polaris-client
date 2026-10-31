"""Custom-sky loading, validation, safe staging, application and restore.

The Roblox cache targets below are copied verbatim from the supplied
skyboxfix/move.bat. That batch file does not identify which target is which
Sky face, so applying requires an explicit one-to-one face mapping.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath

log = logging.getLogger("polaris.custom_sky")

FACES = ("back", "down", "front", "left", "right", "up")
# Exact asset filenames and cache-prefix directories from skyboxfix/move.bat.
SKYBOXFIX_TARGETS = (
    ("a564ec8aeef3614e788d02f0090089d8", "a5"),
    ("7328622d2d509b95dd4dd2c721d1ca8b", "73"),
    ("a50f6563c50ca4d5dcb255ee5cfab097", "a5"),
    ("6c94b9385e52d221f0538aadaceead2d", "6c"),
    ("9244e00ff9fd6cee0bb40a262bb35d31", "92"),
    ("78cb2e93aee0cdbd79b15a866bc93a54", "78"),
)
TARGET_IDS = tuple(item[0] for item in SKYBOXFIX_TARGETS)
MAX_TEXTURE_BYTES = 64 * 1024 * 1024
MAX_ZIP_BYTES = 256 * 1024 * 1024
MAX_ZIP_ENTRIES = 10_000
MAX_ZIP_FILES_TOTAL = 256 * 1024 * 1024

_ALIASES = {
    "back": "back", "bk": "back",
    "down": "down", "dn": "down", "bottom": "down",
    "front": "front", "ft": "front",
    "left": "left", "lf": "left",
    "right": "right", "rt": "right",
    "up": "up", "top": "up",
}


class SkyError(ValueError):
    """A user-correctable custom-sky input or application error."""


def target_path(root: Path, asset_id: str) -> Path:
    """Resolve only an allowlisted cache entry using the batch's prefix rule."""
    if asset_id not in TARGET_IDS:
        raise SkyError(f"Unknown Roblox cache target: {asset_id}")
    prefix = next(prefix for key, prefix in SKYBOXFIX_TARGETS if key == asset_id)
    return Path(root) / prefix / asset_id


def default_target_root(local_app_data: str | Path | None = None) -> Path:
    """Return the exact cache root used by move.bat; never infer a version path."""
    base = local_app_data if local_app_data is not None else os.environ.get("LOCALAPPDATA")
    if not base:
        raise SkyError("LOCALAPPDATA is unavailable; this feature requires Windows Roblox.")
    return Path(base) / "Roblox" / "rbx-storage"


def face_from_filename(filename: str) -> str | None:
    """Identify a Sky face from tokens such as SkyboxBk.tex or sky_front.tex."""
    stem = Path(filename).stem.casefold()
    tokens = re.findall(r"[a-z]+", stem)
    found: set[str] = set()
    for token in tokens:
        if token.startswith("skybox"):
            token = token[6:]
        face = _ALIASES.get(token)
        if face:
            found.add(face)
    compact = re.sub(r"[^a-z]", "", stem)
    if compact.startswith("skybox"):
        compact = compact[6:]
    face = _ALIASES.get(compact)
    if face:
        found.add(face)
    return next(iter(found)) if len(found) == 1 else None


def _validate_texture(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink():
        raise SkyError(f"Symbolic-link texture files are not accepted: {path.name}")
    if not path.is_file():
        raise SkyError(f"Texture file is missing: {path}")
    if path.suffix.casefold() != ".tex":
        raise SkyError(f"Expected a .tex file: {path.name}")
    size = path.stat().st_size
    if size == 0:
        raise SkyError(f"Empty texture file: {path.name}")
    if size > MAX_TEXTURE_BYTES:
        raise SkyError(f"Texture exceeds the 64 MiB safety limit: {path.name}")
    digest = hashlib.sha256()
    head = b""
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            if not head:
                head = block[:4]
            digest.update(block)
    if head.startswith((b"MZ", b"PK\x03\x04", b"\x7fELF")):
        raise SkyError(f"{path.name} is an executable or archive, not a texture payload.")
    # The supplied cache samples use Roblox's RBXH response envelope. When a
    # user file uses that envelope, verify its gzip body instead of trusting
    # the extension. Raw .tex payloads have no format specification in the
    # supplied project, so they are size/emptiness checked only.
    if head == b"RBXH":
        data = path.read_bytes()
        marker = data.find(b"\x1f\x8b", 4)
        if marker < 0:
            raise SkyError(f"Malformed RBXH texture response: {path.name}")
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data[marker:])) as gz:
                decoded = gz.read(MAX_TEXTURE_BYTES + 1)
                if len(decoded) > MAX_TEXTURE_BYTES:
                    raise SkyError(f"Decoded texture exceeds the 64 MiB safety limit: {path.name}")
        except (OSError, EOFError) as exc:
            raise SkyError(f"Corrupt compressed texture payload: {path.name}") from exc
    return {"path": str(path), "name": path.name, "size": size, "sha256": digest.hexdigest()}


def _scan_zip(archive_path: Path) -> tuple[zipfile.ZipFile, list[zipfile.ZipInfo]]:
    archive_path = Path(archive_path)
    if archive_path.is_symlink() or not archive_path.is_file():
        raise SkyError("The selected ZIP file does not exist or is a symbolic link.")
    if archive_path.stat().st_size > MAX_ZIP_BYTES:
        raise SkyError("ZIP exceeds the 256 MiB safety limit.")
    try:
        archive = zipfile.ZipFile(archive_path)
        infos = archive.infolist()
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise SkyError(f"Invalid or damaged ZIP file: {exc}") from exc
    if len(infos) > MAX_ZIP_ENTRIES:
        archive.close()
        raise SkyError("ZIP contains more than 10,000 entries.")
    total = 0
    seen_paths: set[str] = set()
    for info in infos:
        raw = info.filename
        normalized = raw.replace("\\", "/")
        parts = PurePosixPath(normalized).parts
        mode = info.external_attr >> 16
        if ("\x00" in raw or normalized.startswith("/") or
                re.match(r"^[a-zA-Z]:", normalized) or
                any(part in ("..", "") for part in parts) or
                stat.S_ISLNK(mode)):
            archive.close()
            raise SkyError(f"Unsafe ZIP entry path or link was rejected: {raw!r}")
        folded = normalized.casefold()
        if folded in seen_paths:
            archive.close()
            raise SkyError(f"Duplicate ZIP entry name: {raw}")
        seen_paths.add(folded)
        if info.flag_bits & 0x1:
            archive.close()
            raise SkyError(f"Encrypted ZIP entries are not supported: {raw}")
        total += info.file_size
        if info.file_size > MAX_TEXTURE_BYTES and raw.casefold().endswith(".tex"):
            archive.close()
            raise SkyError(f"Texture exceeds the 64 MiB safety limit: {raw}")
        if total > MAX_ZIP_FILES_TOTAL:
            archive.close()
            raise SkyError("ZIP expands beyond the 256 MiB safety limit.")
    return archive, infos


def _choose_faces(entries: list[tuple[str, object]], *, strict: bool) -> dict[str, object]:
    """Select one named .tex per face; reject duplicate or unrecognized direct inputs."""
    selected: dict[str, object] = {}
    names: Counter[str] = Counter()
    for name, value in entries:
        if not name.casefold().endswith(".tex"):
            if strict:
                raise SkyError(f"Expected six .tex files; unsupported input: {name}")
            continue
        names[Path(name).name.casefold()] += 1
        face = face_from_filename(Path(name).name)
        if face is None:
            if strict:
                raise SkyError(f"Cannot identify a Sky direction from filename: {Path(name).name}")
            continue
        if face in selected:
            raise SkyError(f"Duplicate {face} texture: {Path(name).name}")
        selected[face] = value
    repeated = [name for name, count in names.items() if count > 1]
    if repeated:
        raise SkyError(f"Duplicate texture filename: {repeated[0]}")
    missing = [face for face in FACES if face not in selected]
    if missing:
        raise SkyError("Missing Sky directions: " + ", ".join(missing))
    return selected


def _validate_selected(selected: dict[str, Path]) -> dict[str, dict]:
    if set(selected) != set(FACES):
        raise SkyError("Exactly one texture for each of the six Sky directions is required.")
    result = {}
    for face in FACES:
        info = _validate_texture(Path(selected[face]))
        if face_from_filename(info["name"]) != face:
            raise SkyError(f"Filename no longer identifies the {face} direction: {info['name']}")
        result[face] = info
    return result


def load_texture_files(paths: list[str | Path]) -> dict:
    """Validate a direct selection of exactly six direction-named .tex files."""
    if len(paths) != 6:
        raise SkyError(f"Select exactly six .tex files (selected: {len(paths)}).")
    selected = _choose_faces([(Path(p).name, Path(p)) for p in paths], strict=True)
    files = {face: Path(path) for face, path in selected.items()}
    return {"files": {k: str(v) for k, v in files.items()},
            "details": _validate_selected(files)}


def load_texture_folder(folder: str | Path) -> dict:
    """Find direction-named .tex files recursively, ignoring unrelated files."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise SkyError("The selected folder is unavailable or is a symbolic link.")
    entries: list[tuple[str, Path]] = []
    count = 0
    for current, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(current) / d).is_symlink()]
        for name in files:
            count += 1
            if count > MAX_ZIP_ENTRIES:
                raise SkyError("Folder contains more than 10,000 files.")
            path = Path(current) / name
            if path.is_symlink():
                continue
            if path.suffix.casefold() == ".tex":
                entries.append((str(path.relative_to(folder)), path))
    selected = _choose_faces(entries, strict=False)
    files_by_face = {face: Path(path) for face, path in selected.items()}
    return {"files": {k: str(v) for k, v in files_by_face.items()},
            "details": _validate_selected(files_by_face)}


def load_texture_zip(zip_path: str | Path, staging_root: str | Path) -> dict:
    """Safely inspect a ZIP and stage only its six selected .tex files."""
    zip_path, staging_root = Path(zip_path), Path(staging_root)
    archive, infos = _scan_zip(zip_path)
    try:
        entries = [(i.filename.replace("\\", "/"), i) for i in infos if not i.is_dir()]
        selected_info = _choose_faces(entries, strict=False)
        archive_digest = hashlib.sha256()
        with zip_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                archive_digest.update(block)
        destination = staging_root / archive_digest.hexdigest()[:24]
        destination.mkdir(parents=True, exist_ok=True)
        files: dict[str, Path] = {}
        for face in FACES:
            info = selected_info[face]
            output = destination / f"Skybox{face.title()}.tex"
            fd, tmp_name = tempfile.mkstemp(prefix=".sky-", suffix=".tmp", dir=destination)
            try:
                with os.fdopen(fd, "wb") as out, archive.open(info, "r") as src:
                    size = 0
                    digest = hashlib.sha256()
                    while True:
                        block = src.read(1024 * 1024)
                        if not block:
                            break
                        size += len(block)
                        if size > MAX_TEXTURE_BYTES:
                            raise SkyError(f"Texture exceeds the 64 MiB safety limit: {info.filename}")
                        out.write(block)
                        digest.update(block)
                    if size == 0:
                        raise SkyError(f"Empty texture file: {info.filename}")
                    out.flush()
                    os.fsync(out.fileno())
                if size != info.file_size:
                    raise SkyError(f"Incomplete ZIP extraction: {info.filename}")
                os.replace(tmp_name, output)
                files[face] = output
            finally:
                try:
                    os.unlink(tmp_name)
                except FileNotFoundError:
                    pass
        details = _validate_selected(files)
        log.info("custom_sky_zip_loaded source=%s faces=%s", zip_path.name, list(files))
        return {"files": {k: str(v) for k, v in files.items()}, "details": details}
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise SkyError(f"Could not safely read ZIP contents: {exc}") from exc
    finally:
        archive.close()


def validate_face_targets(face_targets: dict[str, str]) -> dict[str, str]:
    """Require an explicit bijection; the supplied batch contains no face labels."""
    if set(face_targets) != set(FACES):
        raise SkyError("Assign a destination to every Sky direction before applying.")
    values = list(face_targets.values())
    if any(value not in TARGET_IDS for value in values):
        raise SkyError("A destination is not one of the six targets from skyboxfix/move.bat.")
    if len(set(values)) != len(TARGET_IDS):
        raise SkyError("Each of the six Roblox cache targets must be used exactly once.")
    return dict(face_targets)


def _write_atomic(source: Path, destination: Path, expected_hash: str | None = None) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink():
        raise SkyError(f"Refusing to write through a symbolic-link directory: {destination.parent}")
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    digest = hashlib.sha256()
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as out:
            for block in iter(lambda: src.read(1024 * 1024), b""):
                digest.update(block)
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        actual = digest.hexdigest()
        if expected_hash and actual != expected_hash:
            raise SkyError(f"Texture changed during apply: {source.name}")
        if destination.exists() and os.name == "nt":
            os.chmod(destination, stat.S_IREAD | stat.S_IWRITE)
        os.replace(temp_name, destination)
        return actual
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _restore_manifest(manifest: dict, backup_dir: Path, root: Path) -> list[Path]:
    restored = []
    records = manifest.get("targets")
    if not isinstance(records, list) or len(records) != len(TARGET_IDS):
        raise SkyError("Custom-sky backup manifest is incomplete.")
    seen = set()
    for record in records:
        asset_id = record.get("asset_id") if isinstance(record, dict) else None
        if asset_id not in TARGET_IDS or asset_id in seen:
            raise SkyError("Custom-sky backup contains an invalid target.")
        seen.add(asset_id)
        destination = target_path(root, asset_id)
        if destination.parent.is_symlink() or destination.is_symlink():
            raise SkyError(f"Refusing to restore through a symbolic link: {destination}")
        if record.get("existed"):
            source = backup_dir / "files" / asset_id
            if source.is_symlink() or not source.is_file():
                raise SkyError(f"Backup file is missing: {asset_id}")
            if destination.exists():
                os.chmod(destination, stat.S_IREAD | stat.S_IWRITE)
            _write_atomic(source, destination, record.get("sha256"))
            try:
                os.chmod(destination, int(record.get("mode", stat.S_IREAD)))
            except OSError:
                log.warning("custom_sky_restore_mode_failed path=%s", destination)
        else:
            if destination.exists():
                if os.name == "nt":
                    os.chmod(destination, stat.S_IREAD | stat.S_IWRITE)
                destination.unlink()
        restored.append(destination)
    return restored


def _snapshot_current_cache(root: Path, backup_root: Path) -> tuple[str, Path]:
    """Capture the current six targets so a failed restore can roll back."""
    if root.is_symlink():
        raise SkyError("The Roblox cache root is a symbolic link; refusing to modify it.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_id = f"custom-sky-pre-restore-{stamp}"
    backup_dir = backup_root / backup_id
    files_dir = backup_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=False)
    try:
        records = []
        for asset_id in TARGET_IDS:
            dest = target_path(root, asset_id)
            if dest.is_symlink() or dest.parent.is_symlink():
                raise SkyError(f"Refusing to back up a symbolic link: {dest}")
            if dest.exists():
                if not dest.is_file():
                    raise SkyError(f"Roblox cache target is not a regular file: {dest}")
                digest = hashlib.sha256()
                with dest.open("rb") as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(block)
                shutil.copy2(dest, files_dir / asset_id)
                records.append({"asset_id": asset_id, "existed": True, "sha256": digest.hexdigest(),
                                "mode": stat.S_IMODE(dest.stat().st_mode)})
            else:
                records.append({"asset_id": asset_id, "existed": False})
        manifest = {
            "id": backup_id, "created_at": datetime.now().isoformat(timespec="seconds"),
            "kind": "pre-restore", "target_root": str(root), "targets": records,
        }
        (backup_dir / "meta.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    return backup_id, backup_dir


def apply_custom_sky(files_by_face: dict[str, str | Path], face_targets: dict[str, str],
                     target_root: str | Path, backup_root: str | Path, version_dir: str | Path) -> dict:
    """Back up the six known cache entries, replace them, verify, and roll back on failure."""
    face_targets = validate_face_targets(face_targets)
    if set(files_by_face) != set(FACES):
        raise SkyError("Exactly six validated texture files are required.")
    checked = _validate_selected({face: Path(files_by_face[face]) for face in FACES})
    version_dir = Path(version_dir)
    player = version_dir / "RobloxPlayerBeta.exe"
    if not player.is_file():
        raise SkyError("The detected Roblox version is no longer valid. Re-detect Roblox and try again.")
    root, backup_root = Path(target_root), Path(backup_root)
    if root.is_symlink():
        raise SkyError("The Roblox cache root is a symbolic link; refusing to modify it.")
    if not root.parent.is_dir():
        raise SkyError(f"Roblox cache parent folder is missing: {root.parent}")
    root.mkdir(parents=True, exist_ok=True)
    for asset_id in TARGET_IDS:
        dest = target_path(root, asset_id)
        if dest.parent.is_symlink() or dest.is_symlink():
            raise SkyError(f"Refusing to overwrite a symbolic link: {dest}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_id = f"custom-sky-{stamp}"
    backup_dir = backup_root / backup_id
    backup_files = backup_dir / "files"
    backup_files.mkdir(parents=True, exist_ok=False)
    records = []
    try:
        # Back up the entire target set before changing any target.
        for asset_id, _prefix in SKYBOXFIX_TARGETS:
            dest = target_path(root, asset_id)
            if dest.exists():
                if not dest.is_file():
                    raise SkyError(f"Roblox cache target is not a regular file: {dest}")
                digest = hashlib.sha256(dest.read_bytes()).hexdigest()
                shutil.copy2(dest, backup_files / asset_id)
                records.append({"asset_id": asset_id, "existed": True, "sha256": digest,
                                "mode": stat.S_IMODE(dest.stat().st_mode)})
            else:
                records.append({"asset_id": asset_id, "existed": False})
        manifest = {
            "id": backup_id, "created_at": datetime.now().isoformat(timespec="seconds"),
            "version_dir": str(version_dir), "target_root": str(root),
            "targets": records,
        }
        manifest_path = backup_dir / "meta.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        applied = []
        for face in FACES:
            asset_id = face_targets[face]
            dest = target_path(root, asset_id)
            if dest.exists() and os.name == "nt":
                os.chmod(dest, stat.S_IREAD | stat.S_IWRITE)
            _write_atomic(Path(files_by_face[face]), dest, checked[face]["sha256"])
            # This mirrors attrib +R from move.bat, but only after verification.
            os.chmod(dest, stat.S_IREAD)
            actual = hashlib.sha256(dest.read_bytes()).hexdigest()
            if actual != checked[face]["sha256"]:
                raise SkyError(f"Post-write verification failed: {dest.name}")
            applied.append({"face": face, "asset_id": asset_id, "sha256": actual})
        log.info("custom_sky_applied backup=%s version=%s targets=%s",
                 backup_id, version_dir.name, [row["asset_id"] for row in applied])
        return {"backup_id": backup_id, "backup_dir": str(backup_dir),
                "version_dir": str(version_dir), "target_root": str(root), "applied": applied}
    except Exception:
        try:
            if (backup_dir / "meta.json").is_file():
                _restore_manifest(json.loads((backup_dir / "meta.json").read_text("utf-8")), backup_dir, root)
            else:
                # Failure while preparing backup: no target has been changed.
                pass
        except Exception:
            log.exception("custom_sky_rollback_failed backup=%s", backup_id)
        raise


def restore_custom_sky(backup_root: str | Path, backup_id: str, target_root: str | Path) -> dict:
    backup_root, root = Path(backup_root), Path(target_root)
    if root.is_symlink():
        raise SkyError("The Roblox cache root is a symbolic link; refusing to modify it.")
    backup_dir = (backup_root / backup_id).resolve()
    try:
        backup_dir.relative_to(backup_root.resolve())
    except ValueError as exc:
        raise SkyError("Invalid custom-sky backup identifier.") from exc
    manifest_path = backup_dir / "meta.json"
    if not manifest_path.is_file():
        raise SkyError("Custom-sky backup was not found.")
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise SkyError(f"Custom-sky backup manifest is damaged: {exc}") from exc
    if manifest.get("target_root") != str(root):
        raise SkyError("Backup belongs to a different Roblox cache location.")
    rollback_id, rollback_dir = _snapshot_current_cache(root, backup_root)
    rollback_manifest = json.loads((rollback_dir / "meta.json").read_text("utf-8"))
    try:
        restored = _restore_manifest(manifest, backup_dir, root)
    except Exception as exc:
        try:
            _restore_manifest(rollback_manifest, rollback_dir, root)
        except Exception:
            log.exception("custom_sky_restore_rollback_failed backup=%s rollback=%s", backup_id, rollback_id)
            raise SkyError(f"Restore failed and rollback was incomplete; recovery backup: {rollback_id}") from exc
        raise
    log.info("custom_sky_restored backup=%s targets=%s rollback=%s",
             backup_id, len(restored), rollback_id)
    return {"paths": [str(path) for path in restored], "rollback_backup_id": rollback_id}


def backup_summary(backup_root: str | Path, backup_id: str) -> dict | None:
    path = Path(backup_root) / backup_id / "meta.json"
    try:
        data = json.loads(path.read_text("utf-8"))
        return {"id": data["id"], "created_at": data["created_at"], "target_root": data["target_root"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def verify_applied_targets(target_root: str | Path, expected: dict[str, str]) -> dict:
    """Check saved target hashes after restart without trusting the old UI state."""
    if set(expected) != set(TARGET_IDS) or any(
            not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
            for value in expected.values()):
        return {"ok": False, "error": "No valid custom-sky target hashes are saved."}
    for asset_id, expected_hash in expected.items():
        path = target_path(Path(target_root), asset_id)
        if path.is_symlink() or not path.is_file():
            return {"ok": False, "error": f"Missing or unsafe target: {asset_id}"}
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected_hash:
            return {"ok": False, "error": f"Target was changed: {asset_id}"}
    return {"ok": True}
