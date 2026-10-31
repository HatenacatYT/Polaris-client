"""Custom-sky input, mapping, apply, rollback and restore tests."""
from __future__ import annotations

import os
from pathlib import Path
import zipfile

import pytest

from polaris.core import custom_sky as sky


NAMES = {
    "back": "SkyboxBk.tex",
    "down": "SkyboxDn.tex",
    "front": "SkyboxFt.tex",
    "left": "SkyboxLf.tex",
    "right": "SkyboxRt.tex",
    "up": "SkyboxUp.tex",
}


def make_textures(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for index, (face, name) in enumerate(NAMES.items()):
        path = folder / name
        path.write_bytes(f"texture-{face}-{index}".encode())
        files[face] = path
    return files


def test_direction_named_files_and_duplicate_detection(tmp_path):
    files = make_textures(tmp_path / "input")
    result = sky.load_texture_files(list(files.values()))
    assert set(result["files"]) == set(sky.FACES)
    assert result["details"]["up"]["name"] == "SkyboxUp.tex"
    duplicate = tmp_path / "another" / "SkyboxBk.tex"
    duplicate.parent.mkdir()
    duplicate.write_bytes(b"duplicate face")
    with pytest.raises(sky.SkyError, match="Duplicate"):
        sky.load_texture_files([files["back"], files["down"], files["front"],
                                files["left"], files["right"], duplicate])


def test_folder_recurses_and_ignores_unrelated_files(tmp_path):
    source = tmp_path / "folder"
    files = make_textures(source / "nested" / "deep")
    (source / "readme.txt").write_text("not a texture")
    (source / "nested" / "unrelated.tex").write_bytes(b"not a named Sky face")
    result = sky.load_texture_folder(source)
    assert set(result["files"]) == set(sky.FACES)
    assert Path(result["files"]["front"]) == files["front"]


def test_zip_extracts_only_six_faces_and_rejects_traversal(tmp_path):
    source = tmp_path / "source"
    files = make_textures(source / "deep" / "folder")
    archive = tmp_path / "sky.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("unrelated/readme.txt", b"ignored")
        for file in files.values():
            z.write(file, f"deep/nested/{file.name}")
    result = sky.load_texture_zip(archive, tmp_path / "staging")
    assert set(result["files"]) == set(sky.FACES)
    assert all(Path(path).is_file() for path in result["files"].values())
    assert all(Path(path).parent.name == sky.hashlib.sha256(archive.read_bytes()).hexdigest()[:24]
               for path in result["files"].values())

    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as z:
        z.writestr("../outside/SkyboxBk.tex", b"bad")
    with pytest.raises(sky.SkyError, match="Unsafe ZIP"):
        sky.load_texture_zip(unsafe, tmp_path / "staging-unsafe")


def test_invalid_and_empty_inputs_are_explained(tmp_path):
    empty = tmp_path / "SkyboxBk.tex"
    empty.write_bytes(b"")
    with pytest.raises(sky.SkyError, match="Empty"):
        sky._validate_texture(empty)
    malformed = tmp_path / "SkyboxBk.tex"
    malformed.write_bytes(b"RBXHresponse without gzip")
    with pytest.raises(sky.SkyError, match="Malformed RBXH"):
        sky._validate_texture(malformed)
    with pytest.raises(sky.SkyError, match="Assign a destination"):
        sky.validate_face_targets({})


def test_apply_creates_backup_and_restore_returns_original_contents(tmp_path):
    files = make_textures(tmp_path / "input")
    root = tmp_path / "LocalAppData" / "Roblox" / "rbx-storage"
    root.parent.mkdir(parents=True)
    version = tmp_path / "Versions" / "version-test"
    version.mkdir(parents=True)
    (version / "RobloxPlayerBeta.exe").write_bytes(b"test stub")
    backup_root = tmp_path / "backups"

    # One pre-existing read-only file; the other five are created by apply.
    target = sky.target_path(root, sky.TARGET_IDS[0])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"before")
    os.chmod(target, 0o400)

    result = sky.apply_custom_sky(
        {face: str(path) for face, path in files.items()},
        dict(zip(sky.FACES, sky.TARGET_IDS)),
        root, backup_root, version,
    )
    assert result["backup_id"].startswith("custom-sky-")
    for face, asset_id in zip(sky.FACES, sky.TARGET_IDS):
        assert sky.target_path(root, asset_id).read_bytes() == files[face].read_bytes()
    assert sky.verify_applied_targets(root, {row["asset_id"]: row["sha256"] for row in result["applied"]})["ok"]

    sky.restore_custom_sky(backup_root, result["backup_id"], root)
    assert target.read_bytes() == b"before"
    assert target.stat().st_mode & 0o222 == 0
    for asset_id in sky.TARGET_IDS[1:]:
        assert not sky.target_path(root, asset_id).exists()


def test_apply_failure_rolls_back_partial_writes(tmp_path, monkeypatch):
    files = make_textures(tmp_path / "input")
    root = tmp_path / "Roblox" / "rbx-storage"
    root.parent.mkdir()
    version = tmp_path / "Versions" / "version-test"
    version.mkdir(parents=True)
    (version / "RobloxPlayerBeta.exe").write_bytes(b"test stub")
    backup_root = tmp_path / "backups"
    first = sky.target_path(root, sky.TARGET_IDS[0])
    first.parent.mkdir(parents=True)
    first.write_bytes(b"original")
    original_write = sky._write_atomic
    texture_writes = 0

    def fail_on_third_texture(source, destination, expected_hash=None):
        nonlocal texture_writes
        if Path(source) in files.values():
            texture_writes += 1
            if texture_writes == 3:
                raise OSError("simulated disk failure")
        return original_write(source, destination, expected_hash)

    monkeypatch.setattr(sky, "_write_atomic", fail_on_third_texture)
    with pytest.raises(OSError, match="simulated disk failure"):
        sky.apply_custom_sky(
            {face: str(path) for face, path in files.items()},
            dict(zip(sky.FACES, sky.TARGET_IDS)),
            root, backup_root, version,
        )
    assert first.read_bytes() == b"original"
    assert not sky.target_path(root, sky.TARGET_IDS[1]).exists()
    assert not sky.target_path(root, sky.TARGET_IDS[2]).exists()


def test_restore_failure_rolls_back_to_the_applied_sky(tmp_path, monkeypatch):
    files = make_textures(tmp_path / "input")
    root = tmp_path / "Roblox" / "rbx-storage"
    root.parent.mkdir()
    version = tmp_path / "Versions" / "version-test"
    version.mkdir(parents=True)
    (version / "RobloxPlayerBeta.exe").write_bytes(b"test stub")
    backup_root = tmp_path / "backups"
    for index, asset_id in enumerate(sky.TARGET_IDS):
        target = sky.target_path(root, asset_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"before-{index}".encode())
    applied = sky.apply_custom_sky(
        {face: str(path) for face, path in files.items()},
        dict(zip(sky.FACES, sky.TARGET_IDS)),
        root, backup_root, version,
    )
    original_write = sky._write_atomic
    restore_writes = 0
    original_backup_files = Path(applied["backup_dir"]) / "files"

    def fail_during_restore(source, destination, expected_hash=None):
        nonlocal restore_writes
        if Path(source).parent == original_backup_files:
            restore_writes += 1
            if restore_writes == 3:
                raise OSError("simulated restore failure")
        return original_write(source, destination, expected_hash)

    monkeypatch.setattr(sky, "_write_atomic", fail_during_restore)
    with pytest.raises(OSError, match="simulated restore failure"):
        sky.restore_custom_sky(backup_root, applied["backup_id"], root)
    for face, asset_id in zip(sky.FACES, sky.TARGET_IDS):
        assert sky.target_path(root, asset_id).read_bytes() == files[face].read_bytes()
