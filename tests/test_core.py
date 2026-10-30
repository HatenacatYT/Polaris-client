"""ユニットテスト（モック使用。Robloxの実環境には依存しない）。"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from polaris.core.app import Core
from polaris.core.paths import AppPaths
from polaris.core.jsonio import read_json, write_json, StorageError, RECOVERY_NOTES
from polaris.core.games import (parse_place_input, InvalidPlace, build_launch_uri, uri_place_id, GameLibrary)
from polaris.core.flags import (loads_checked, parse_value_text, to_roblox_payload, diff_payload, FlagStore,
                                PresetStore, validate_flag, EDITOR_PRESET_ID)
from polaris.core.roblox import Detector, RobloxNotFound, RobloxAmbiguous, PLAYER_EXE
from polaris.core.backup import BackupManager, RestoreError
from polaris.core.allowlist import AllowlistStore, AllowlistError, extract_flag_names
from polaris.core.launcher import Launcher


def mk_version(root: Path, name: str, with_exe=True) -> Path:
    d = root / "Versions" / name
    d.mkdir(parents=True)
    if with_exe:
        (d / PLAYER_EXE).write_bytes(b"x")
    return d


@pytest.fixture
def env(tmp_path):
    roots = tmp_path / "Roblox"
    calls = {"uri": [], "exe": []}
    det = Detector(roots=[roots / "Versions"], registry_fn=lambda: None, official_fn=lambda: None)
    core = Core(AppPaths(tmp_path / "data"), detector=det, launcher_kwargs=dict(
        open_uri=lambda u: calls["uri"].append(u), open_exe=lambda p: calls["exe"].append(p),
        process_running=lambda: True, net_check=lambda: True, sleep=lambda s: None))
    return core, roots, calls, det


# ---- Place ID / URL ----
@pytest.mark.parametrize("t,exp", [
    ("920587237", 920587237), (" 123 ", 123),
    ("https://www.roblox.com/games/920587237/Adopt-Me", 920587237),
    ("https://www.roblox.com/ja/games/606849621/Jailbreak?privateServerLinkCode=1", 606849621),
    ("roblox.com/games/5", 5)])
def test_place_ok(t, exp):
    assert parse_place_input(t) == exp


@pytest.mark.parametrize("t", ["", "abc", "0", "-5", "12.5", "99999999999999999999",
                               "http://www.roblox.com/games/1", "https://evil.com/games/1",
                               "https://www.roblox.com@evil.com/games/1", "https://www.roblox.com/users/1",
                               "https://www.roblox.com.evil.com/games/1", "１２３", "roblox://placeId=1"])
def test_place_bad(t):
    with pytest.raises(InvalidPlace):
        parse_place_input(t)


def test_uri_roundtrip():
    u = build_launch_uri(1818)
    assert u == "roblox://experiences/start?placeId=1818" and uri_place_id(u) == 1818
    assert uri_place_id("roblox://experiences/start?placeId=1&placeId=2") is None


# ---- JSON ----
def test_json_missing_and_corrupt(tmp_path):
    p = tmp_path / "a.json"
    assert read_json(p, {"d": 1}) == {"d": 1}
    write_json(p, {"v": 1}); write_json(p, {"v": 2})
    p.write_text("{broken", encoding="utf-8")
    assert read_json(p, {}) == {"v": 1}           # .bak から復旧
    assert RECOVERY_NOTES and any(tmp_path.glob("a.json.corrupt-*"))
    (tmp_path / "a.json.bak").write_text("zzz"); p.write_text("{x")
    assert read_json(p, {"fallback": True}) == {"fallback": True}


def test_json_nan_rejected(tmp_path):
    with pytest.raises(StorageError):
        write_json(tmp_path / "n.json", {"a": float("nan")})
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="権限テストはroot/Windowsでは不可")
def test_write_permission_denied(tmp_path):
    d = tmp_path / "ro"; d.mkdir(); d.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(StorageError):
            write_json(d / "x.json", {})
    finally:
        d.chmod(stat.S_IRWXU)


def test_loads_checked_dups_and_errors():
    d, dups, errs = loads_checked('{"FFlagAbc": "True", "FFlagAbc": "False"}')
    assert dups == ["FFlagAbc"] and d["FFlagAbc"] == "False" and not errs
    assert loads_checked("{oops")[0] is None
    assert loads_checked("[1]")[2]
    assert loads_checked('{"bad name": 1}')[2]
    assert loads_checked('{"FFlagOk": [1]}')[2]
    assert loads_checked('{"FIntX": NaN}')[2]


def test_parse_value_and_payload():
    assert parse_value_text("true") is True and parse_value_text("12") == 12 and parse_value_text("True") == "True"
    with pytest.raises(ValueError):
        parse_value_text("[1]")
    assert to_roblox_payload({"FFlagA": True, "FIntB": 5, "FStringC": "x"}) == {"FFlagA": "True", "FIntB": "5", "FStringC": "x"}
    assert to_roblox_payload({"FFlagA": True}, "native") == {"FFlagA": True}
    assert diff_payload({"A": "1", "B": "1"}, {"A": "2", "C": "1"}).removed == {"B": "1"}


# ---- FlagStore / Preset ----
def test_flag_crud(tmp_path):
    s = FlagStore(tmp_path / "f.json")
    s.add("FFlagTestOne", True, "UI"); s.add("FIntTestTwo", 5)
    with pytest.raises(ValueError):
        s.add("FFlagTestOne", False)
    with pytest.raises(ValueError):
        s.add("bad name", 1)
    s.update_value("FIntTestTwo", 9); s.set_attr(["FFlagTestOne"], enabled=False, favorite=True)
    s.rename("FIntTestTwo", "FIntTestThree")
    s2 = FlagStore(tmp_path / "f.json")
    assert s2.flags["FIntTestThree"].value == 9 and not s2.flags["FFlagTestOne"].enabled
    assert s2.enabled_dict() == {"FIntTestThree": 9}
    s2.delete(["FFlagTestOne"]); assert "FFlagTestOne" not in FlagStore(tmp_path / "f.json").flags


def test_preset_crud(tmp_path):
    p = PresetStore(tmp_path / "p.json")
    a = p.create("A", "UI", {"FFlagAaa": True}); b = p.duplicate(a["id"])
    assert b["name"].endswith("(copy)") and len(PresetStore(tmp_path / "p.json").presets) == 2
    with pytest.raises(ValueError):
        p.create("", "UI")
    p.delete(a["id"]); assert p.get(a["id"]) is None


def test_games_library(tmp_path):
    g = GameLibrary(tmp_path / "g.json")
    x = g.add("https://www.roblox.com/games/42/x", "テスト")
    with pytest.raises(ValueError):
        g.add("42")
    g.record_launch(x.id); g.update(x.id, favorite=True, note="m")
    g2 = GameLibrary(tmp_path / "g.json")
    assert g2.games[0].launch_count == 1 and g2.search("テ") and g2.favorites() and g2.recent()
    g2.delete(x.id); assert not GameLibrary(tmp_path / "g.json").games


# ---- Roblox 検出 ----
def test_not_installed(env):
    with pytest.raises(RobloxNotFound):
        env[3].detect()


def test_invalid_dir_ignored(env):
    _, roots, _, det = env
    mk_version(roots, "version-aaa", with_exe=False)
    with pytest.raises(RobloxNotFound):
        det.detect()


def test_multiple_versions_and_update(env):
    _, roots, _, det = env
    a = mk_version(roots, "version-old"); b = mk_version(roots, "version-new")
    os.utime(b, (1, 1))                       # 更新日時は判断根拠にしない
    with pytest.raises(RobloxAmbiguous) as ei:
        det.detect()
    assert set(ei.value.candidates) == {a, b}
    det.official_fn = lambda: "version-new"
    assert det.detect().version_dir == b
    det.official_fn = lambda: None; det.registry_fn = lambda: a
    assert det.detect().version_dir == a
    det.registry_fn = lambda: None; det.pinned_fn = lambda: str(b)
    assert det.detect().version_dir == b
    # 更新後: 新フォルダ出現・旧削除でも再検出できる
    import shutil
    shutil.rmtree(a); shutil.rmtree(b); c = mk_version(roots, "version-zzz")
    det.pinned_fn = lambda: str(b)
    assert det.detect().version_dir == c


# ---- バックアップ ----
def test_backup_restore_and_prune(tmp_path):
    bm = BackupManager(lambda: tmp_path / "bk")
    t = tmp_path / "Versions" / "v" / "ClientSettings" / "ClientAppSettings.json"
    t.parent.mkdir(parents=True); t.write_text('{"FFlagAaa": "True"}')
    e = bm.create("roblox", "t", [t]); t.write_text('{"FFlagAaa": "False"}')
    bm.restore(e.id)
    assert json.loads(t.read_text()) == {"FFlagAaa": "True"}
    assert any(x.kind == "pre-restore" for x in bm.list())
    for _ in range(3):
        bm.create("roblox", "x", [t])
    assert bm.prune(2, 0) >= 3 and len(bm.list()) == 2


def test_restore_rejects_bad_target(tmp_path):
    bm = BackupManager(lambda: tmp_path / "bk")
    f = tmp_path / "evil.json"; f.write_text("{}")
    e = bm.create("x", "t", [f])
    with pytest.raises(RestoreError):
        bm.restore(e.id)


def test_restore_missing_roblox_dir(tmp_path):
    bm = BackupManager(lambda: tmp_path / "bk")
    t = tmp_path / "V" / "ClientSettings" / "ClientAppSettings.json"
    t.parent.mkdir(parents=True); t.write_text("{}")
    e = bm.create("roblox", "t", [t])
    import shutil; shutil.rmtree(tmp_path / "V")
    with pytest.raises(RestoreError):
        bm.restore(e.id)


# ---- 許可リスト ----
def test_allowlist(tmp_path):
    a = AllowlistStore(tmp_path / "al.json")
    assert a.status("FFlagX") == "unverified"
    html = "<ul><li>FFlagHandleAltEnterFullscreenManually</li><li>DFIntTextureQualityOverride</li></ul>"
    assert extract_flag_names(html) == {"FFlagHandleAltEnterFullscreenManually", "DFIntTextureQualityOverride"}
    n = a.refresh_online(lambda url: {"post_stream": {"posts": [{"cooked": html}, {"cooked": "FFlagFromComment"}]}})
    assert n == 2 and a.status("DFIntTextureQualityOverride") == "allowed" and a.status("FFlagFromComment") == "not_listed"
    stale = AllowlistStore(tmp_path / "al.json", now=lambda: __import__("datetime").datetime.now() + __import__("datetime").timedelta(days=3))
    assert stale.status("DFIntTextureQualityOverride") == "unverified"   # 古い情報は最新扱いしない
    from polaris.core.net import NetworkError
    def boom(url): raise NetworkError("offline")
    with pytest.raises(AllowlistError):
        a.refresh_online(boom)


# ---- 起動フロー（モック） ----
def test_launch_full_flow(env):
    core, roots, calls, det = env
    v = mk_version(roots, "version-1")
    core.flags.add("FFlagTestOne", True); core.flags.add("FIntTestTwo", 3)
    g = core.games.add("https://www.roblox.com/games/777/x", "G")
    core.games.update(g.id, preset_id=EDITOR_PRESET_ID)
    plan = core.launcher.prepare(g, "apply_and_play")
    assert plan.ok and plan.apply_needed and set(plan.diff.added) == {"FFlagTestOne", "FIntTestTwo"} and plan.unverified
    res = core.launcher.execute(plan)
    assert res.ok and res.applied and res.process_seen and calls["uri"] == ["roblox://experiences/start?placeId=777"]
    assert json.loads((v / "ClientSettings" / "ClientAppSettings.json").read_text()) == {"FFlagTestOne": "True", "FIntTestTwo": "3"}
    assert core.games.get(g.id).launch_count == 1 and "確認できません" in res.message
    # 2回目: 既存ファイルがあるのでバックアップが作られる
    core.flags.update_value("FIntTestTwo", 4)
    res = core.launcher.execute(core.launcher.prepare(g, "apply_and_play"))
    assert res.ok and any(b.kind == "roblox" for b in core.backups.list())


def test_launch_without_apply_and_errors(env):
    core, roots, calls, _ = env
    g = core.games.add("5", "G")
    p = core.launcher.prepare(g, "play_only")
    assert p.error_code == "NOT_FOUND"                       # 未インストール
    mk_version(roots, "version-1")
    p = core.launcher.prepare(g, "play_only")
    assert p.ok and not p.apply_needed
    assert core.launcher.execute(p).ok and calls["uri"]
    bad = core.games.add("6", "B"); bad.place_id = -1
    assert core.launcher.prepare(bad, "play_only").error_code == "INVALID_PLACE"
    mk_version(roots, "version-2")                           # 複数で曖昧
    assert core.launcher.prepare(g, "play_only").error_code == "AMBIGUOUS"


def test_uri_failure_and_apply_failure(env, monkeypatch):
    core, roots, calls, _ = env
    v = mk_version(roots, "version-1")
    g = core.games.add("5", "G"); core.flags.add("FFlagTestOne", True)
    core.games.update(g.id, preset_id=EDITOR_PRESET_ID)
    def boom(u): raise OSError("no handler")
    core.launcher.open_uri = boom
    r = core.launcher.execute(core.launcher.prepare(g, "apply_and_play"))
    assert not r.ok and r.code == "URI_FAILED"
    # 適用中の書き込みエラー → ロールバックして失敗扱い、元ファイル維持
    t = v / "ClientSettings" / "ClientAppSettings.json"; t.write_text('{"Keep": "1"}')
    import polaris.core.applier as ap
    monkeypatch.setattr(ap, "write_json", lambda *a, **k: (_ for _ in ()).throw(StorageError("disk full")))
    core.launcher.open_uri = lambda u: calls["uri"].append(u)
    r = core.launcher.execute(core.launcher.prepare(g, "apply_and_play"))
    assert not r.ok and r.code == "APPLY_FAILED" and json.loads(t.read_text()) == {"Keep": "1"} and not calls["uri"]
    # 適用に失敗しても、ユーザーが選べば適用せず起動できる
    r = core.launcher.execute(core.launcher.prepare(g, "apply_and_play"), apply=False)
    assert r.ok and calls["uri"]


def test_settings_missing_and_corrupt(tmp_path):
    p = AppPaths(tmp_path / "d")
    (p.root / "app_settings.json").write_text("{not json")
    (p.root / "games.json").write_text('{"games": [{"id": "1", "name": "x", "place_id": "bad"}]}')
    c = Core(p)
    assert c.settings.data.animations is True and c.games.games == []     # 破損/不正でも起動できる
    assert any(p.root.glob("app_settings.json.corrupt-*"))


def test_log_redaction(env):
    from polaris.core.logsetup import redact
    assert "SECRET" not in redact(".ROBLOSECURITY=SECRETVALUE token: SECRET2")


def test_build_files_are_ascii_and_bat_is_crlf():
    """日本語Windows(cp932)や英語ランナー(cp1252)でビルドが文字コードで失敗しないよう、ビルド用ファイルはASCIIのみ。"""
    root = Path(__file__).resolve().parent.parent
    for rel in ("run.bat", "run_tests.bat", "build_exe.bat", "build_exe_onedir.bat", "polaris.spec", ".github/workflows/build.yml", "requirements.txt", "requirements-dev.txt"):
        data = (root / rel).read_bytes()
        assert all(b < 128 for b in data), f"{rel} に非ASCII文字があります"
        if rel.endswith(".bat"):
            assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b""), f"{rel} はCRLFである必要があります"


def test_backup_ids_never_collide(tmp_path):
    bm = BackupManager(lambda: tmp_path / "bk")
    f = tmp_path / "ClientAppSettings.json"; f.write_text("{}")
    ids = {bm.create("roblox", "x", [f]).id for _ in range(30)}      # 同一ミリ秒に連続作成
    assert len(ids) == 30 and len(bm.list()) == 30
