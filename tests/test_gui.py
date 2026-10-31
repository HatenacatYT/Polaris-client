"""GUIテスト（オフスクリーン）。起動/スプラッシュ・画面遷移・設定の永続化・FastFlags操作・背景動画。"""
import json
import os
import shutil
import subprocess
import time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from polaris.core.app import Core
from polaris.core.i18n import set_language
from polaris.core.jsonio import RECOVERY_NOTES
from polaris.core.paths import AppPaths
from polaris.core.roblox import Detector, PLAYER_EXE
from polaris.ui import theme
from polaris.ui.main_window import MainWindow
from polaris.ui.widgets import ANIM


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    theme.apply_theme(a)
    return a


def make_core(tmp_path, calls=None):
    v = tmp_path / "R" / "Versions" / "version-x"; v.mkdir(parents=True, exist_ok=True); (v / PLAYER_EXE).write_bytes(b"x")
    calls = calls if calls is not None else []
    core = Core(AppPaths(tmp_path / "d"), detector=Detector(roots=[tmp_path / "R" / "Versions"], registry_fn=lambda: None, official_fn=lambda: None),
                launcher_kwargs=dict(open_uri=calls.append, process_running=lambda: True, net_check=lambda: True, sleep=lambda s: None))
    core.settings.data.auto_check_allowlist = False
    return core


@pytest.fixture
def win(app, tmp_path):
    RECOVERY_NOTES.clear(); set_language("ja"); ANIM["on"] = True
    calls = []
    w = MainWindow(make_core(tmp_path, calls)); w.calls = calls; w.show()
    yield w
    w.close(); w.deleteLater(); app.processEvents(); set_language("ja")


def wait(app, cond, ms=3000):
    for _ in range(ms // 20):
        app.processEvents()
        if cond(): return True
        QTest.qWait(20)
    return False


# ---------------- 起動・スプラッシュ ----------------
def test_startup_splash_min_1s_and_transition(app, tmp_path):
    from polaris.main import Startup
    RECOVERY_NOTES.clear(); ANIM["on"] = True
    res = {}
    st = Startup(app, core_factory=lambda: make_core(tmp_path), min_ms=1000)
    orig = st._show_main
    st._show_main = lambda core: (res.setdefault("t_main", time.monotonic()), orig(core))
    st.ready.connect(lambda w: res.setdefault("win", w))
    t0 = time.monotonic(); st.start()
    assert st.splash.isVisible() and st.splash.windowFlags() & 0x800      # 枠なし
    assert wait(app, lambda: "t_main" in res, 4000)
    assert res["t_main"] - t0 >= 0.99                                     # 初期化が即完了しても最低1秒は表示
    assert wait(app, lambda: "win" in res, 4000)
    w = res["win"]
    assert w.isVisible() and w.windowOpacity() == 1.0 and not st.splash.isVisible()
    assert w.windowFlags() & 0x800 and len(w.grips) == 8 and w.current == "home"
    w.close()


def test_startup_failure_does_not_hang(app, monkeypatch):
    from polaris.main import Startup
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a))
    def boom(): raise RuntimeError("init failed")
    st = Startup(app, core_factory=boom); fails = []; st.failed.connect(fails.append)
    monkeypatch.setattr(app, "exit", lambda c=0: None)
    st.start()
    assert wait(app, lambda: fails, 3000) and shown and "init failed" in str(shown[0])


# ---------------- 画面遷移・ホーム ----------------
@pytest.mark.parametrize("anim", [True, False])
def test_rapid_page_switching(app, win, anim):
    ANIM["on"] = anim
    names = list(win.pages)
    for n in names * 4 + ["settings", "flags", "home", "logs", "status", "backups", "games", "settings"]:
        win.goto(n); QTest.qWait(5)
    wait(app, lambda: win.stack._group is None, 1500)
    assert win.current == "settings" and win.stack.currentWidget() is win.pages["settings"] and win.stack.currentWidget().graphicsEffect() is None


def test_home_buttons_navigate_and_play(app, win, monkeypatch):
    home = win.pages["home"]
    home.gear.click(); assert win.navigation._opened and win.current == "home"
    win.nav["settings"].click(); assert win.current == "settings" and not win.navigation._opened
    win.goto("home"); home.sky.click(); assert win.current == "custom_sky"
    win.goto("home"); home.ff.click(); assert win.current == "flags"
    win.goto("home")
    monkeypatch.setattr("polaris.ui.home.QMenu.exec", lambda *a, **k: None)
    g = win.core.games.add("https://www.roblox.com/games/123/x", "テスト"); win.core.select_game(g.id); win.refresh_all()
    assert "テスト" in home.game_btn.text()
    monkeypatch.setattr("polaris.ui.launch_ui.choose", lambda *a, **k: 0)
    win.core.settings.data.default_launch_mode = "play_only"
    home.play.click()
    assert home.play._busy or wait(app, lambda: win.calls)
    assert wait(app, lambda: win.calls == ["roblox://experiences/start?placeId=123"])
    assert wait(app, lambda: not win.launch.busy and not home.play._busy)
    assert win.core.games.get(g.id).launch_count == 1 and "確認できません" in win.pages["status"].out.toPlainText()


def test_navigation_drawer_outside_click_escape_and_responsive_home(app, win):
    home = win.pages["home"]
    home.gear.click()
    assert win.navigation.isVisible() and win.navigation._opened
    win.navigation.scrim.click()
    assert wait(app, lambda: not win.navigation.isVisible())

    home.gear.click()
    assert win.navigation._opened
    win.escape_shortcut.activated.emit()
    assert wait(app, lambda: not win.navigation.isVisible())

    home.resize(600, 500); app.processEvents()
    assert home.btn_row.direction().name == "TopToBottom"
    home.resize(820, 600); app.processEvents()
    assert home.btn_row.direction().name == "LeftToRight"
    assert home.sky.minimumHeight() == home.play.minimumHeight() == home.ff.minimumHeight()


def test_play_without_game_guides_user(app, win):
    win.pages["home"].play.click()
    assert win.current == "games" and not win.calls


def test_sidebar_toast_and_titlebar(app, win):
    win.set_collapsed(True); win.set_collapsed(False)
    for i in range(8): win.toast.show(f"m{i}", "ok", 100)
    assert len(win.toast.items) <= 4
    assert wait(app, lambda: not win.toast.items, 2500)
    win.toggle_max(); app.processEvents(); win.toggle_max()


# ---------------- 設定の永続化 ----------------
def test_settings_persist_across_restart(app, tmp_path, win):
    sp = win.pages["settings"]
    sp._accent("green"); sp.rb_video.setChecked(True)
    mp4 = tmp_path / "bg.mp4"; mp4.write_bytes(b"x")
    s = win.core.settings.data; s.bg_video_path = str(mp4); sp._save(False)
    sp.loop.setChecked(False); sp.overlay_s().setValue(50); sp._deb.stop(); sp._save(False)
    s.sidebar_collapsed = True; sp._save(False)
    win.core.settings.save()
    c2 = Core(win.core.paths)
    d = c2.settings.data
    assert (d.accent, d.bg_mode, d.bg_video_path, d.bg_loop, d.bg_overlay) == ("green", "video", str(mp4), False, 50)
    # 動画 → アニメーションへ切替えても動画パスは保持される
    sp.rb_anim.setChecked(True)
    assert Core(win.core.paths).settings.data.bg_video_path == str(mp4) and Core(win.core.paths).settings.data.bg_mode == "animated"


def test_language_switch_translates_ui(app, win):
    sp = win.pages["settings"]
    sp.lang.setCurrentIndex(sp.lang.findData("en"))
    assert wait(app, lambda: win.pages["flags"].title and win.nav["games"].text().endswith("Game Library"))
    assert win.core.settings.data.language == "en" and Core(win.core.paths).settings.data.language == "en"
    assert "Play" in win.pages["home"].play.text() or "▶" in win.pages["home"].play.text()
    win.goto("settings"); sp2 = win.pages["settings"]
    sp2.lang.setCurrentIndex(sp2.lang.findData("ja"))
    assert wait(app, lambda: win.nav["games"].text().endswith("ゲームライブラリ"))


def test_ampersand_in_english_labels_is_shown(app, win):
    from polaris.core.i18n import set_language
    set_language("en"); win.set_collapsed(False)
    assert "Backup && Restore" in win.nav["backups"].text()      # 実表示は「Backup & Restore」
    set_language("ja")


def test_theme_accent_applies(app, win):
    win.pages["settings"]._accent("red")
    assert theme.accent() == theme.PRESET_COLORS["red"]
    win.core.settings.data.accent = "cyan"; win.apply_appearance()


def test_corrupt_settings_still_starts(app, tmp_path):
    p = AppPaths(tmp_path / "x"); (p.root / "app_settings.json").write_text("{bad"); (p.root / "presets.json").write_text("[1,2")
    RECOVERY_NOTES.clear()
    c = Core(p)
    assert c.settings.data.language == "ja" and c.presets.presets == [] and RECOVERY_NOTES


# ---------------- FastFlags ----------------
def test_presets_flow(app, win, monkeypatch, tmp_path):
    fp, ed = win.pages["flags"], win.pages["editor"]
    pres = win.core.presets
    win.goto("flags"); assert fp.box.count() == 1                        # 空の案内カード
    a = pres.create("A", "UI", {"FFlagTestOne": True}, "説明"); b = pres.create("B", "その他", {})
    win.refresh_all(); assert fp.box.count() == 2
    # 同名作成の衝突 → 別名で作成
    monkeypatch.setattr("polaris.ui.fastflags.choose", lambda *a_, **k: 1)
    pid = fp._create_resolving("a", "UI", "", {}); assert pres.get(pid)["name"] == "a (2)"
    # 使用する
    fp._do_use(a["id"]); assert win.core.settings.data.active_preset == a["id"] and Core(win.core.paths).settings.data.active_preset == a["id"]
    # 名前変更（重複は不可、空は不可）
    class FakeName:
        def __init__(self, *args, **kw): self.v, self.chk = "B2", args[4]
        def exec(self): assert self.chk("A") and self.chk("") and not self.chk("Zed") and not self.chk("B"); return True
        def value(self): return self.v
    monkeypatch.setattr("polaris.ui.fastflags.NameDialog", FakeName)
    fp._do_rename(b["id"]); assert pres.get(b["id"])["name"] == "B2"
    # 削除: キャンセルでは残る / 確認で削除され使用中は解除
    monkeypatch.setattr("polaris.ui.fastflags.choose", lambda *a_, **k: 1); fp._do_delete(a["id"]); assert pres.get(a["id"])
    monkeypatch.setattr("polaris.ui.fastflags.choose", lambda *a_, **k: 0); fp._do_delete(a["id"])
    assert pres.get(a["id"]) is None and win.core.settings.data.active_preset == ""
    # 編集 → キャンセルでは元データは変わらない
    c = pres.create("C", "UI", {"FFlagKeep": 1})
    win.edit_preset(c["id"]); assert win.current == "editor"
    ed.n_in.setText("FFlagNewOne"); ed.v_in.setText("true"); ed.add()
    ed.n_in.setText("FFlagNewOne"); ed.v_in.setText("false"); ed.add()              # 重複は追加されない
    assert list(ed.work) == ["FFlagKeep", "FFlagNewOne"] and ed.dirty() and "既に存在" in ed.msg.text()
    monkeypatch.setattr("polaris.ui.fastflags.choose", lambda *a_, **k: 0); ed.cancel()
    assert win.current == "flags" and pres.get(c["id"])["flags"] == {"FFlagKeep": 1}
    # 編集 → 保存で反映（型を保持）
    win.edit_preset(c["id"]); ed.n_in.setText("FFlagNewOne"); ed.v_in.setText("true"); ed.add(); ed.save()
    assert Core(win.core.paths).presets.get(c["id"])["flags"] == {"FFlagKeep": 1, "FFlagNewOne": True}
    # 不正な値の編集は拒否
    ed.n_in.setText("bad name"); ed.v_in.setText("1"); ed.add(); assert "bad name" not in ed.work
    ed.save_as  # 別名保存の存在確認


def test_import_export_and_invalid_json(app, win, monkeypatch, tmp_path):
    from polaris.ui import fastflags as ff
    fp, ed = win.pages["flags"], win.pages["editor"]
    shown = []
    monkeypatch.setattr(ff.TextDialog, "exec", lambda self: shown.append(self.windowTitle()) or 0)
    bad = tmp_path / "bad.json"; bad.write_text('{"FFlagA1": [1], "x y": 1')
    monkeypatch.setattr(ff.QFileDialog, "getOpenFileName", lambda *a, **k: (str(bad), ""))
    fp.import_(); assert shown and not win.core.presets.presets          # クラッシュせずエラー表示のみ
    good = tmp_path / "good.json"; good.write_text('{"FFlagAbc": "True", "FIntXyz": 5}')
    monkeypatch.setattr(ff.QFileDialog, "getOpenFileName", lambda *a, **k: (str(good), ""))
    fp.import_(); p = win.core.presets.presets[0]
    assert p["flags"] == {"FFlagAbc": "True", "FIntXyz": 5}
    out = tmp_path / "out.json"
    monkeypatch.setattr(ff.QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    fp._do_export(p["id"]); assert json.loads(out.read_text())["flags"] == p["flags"]
    win.edit_preset(p["id"]); monkeypatch.setattr(ff, "choose", lambda *a, **k: 0)
    ed.export(); assert json.loads(out.read_text()) == {"FFlagAbc": "True", "FIntXyz": "5"}


def test_apply_active_preset_writes_roblox_file(app, win, monkeypatch, tmp_path):
    p = win.core.presets.create("P", "UI", {"FFlagTestOne": True}); win.core.settings.data.active_preset = p["id"]
    monkeypatch.setattr("polaris.ui.launch_ui.TextDialog.exec", lambda self: 1)
    win.goto("flags"); win.pages["flags"].apply_now()
    f = tmp_path / "R" / "Versions" / "version-x" / "ClientSettings" / "ClientAppSettings.json"
    assert wait(app, lambda: f.exists()) and json.loads(f.read_text()) == {"FFlagTestOne": "True"}
    assert wait(app, lambda: not win.launch.busy)
    st = win.core.preset_apply_state(p["id"]); assert st[0] == "applied"


def test_unsaved_editor_blocks_navigation(app, win, monkeypatch):
    c = win.core.presets.create("C", "UI", {"FFlagKeep": 1}); win.edit_preset(c["id"])
    ed = win.pages["editor"]; ed.work["FFlagTmpx"] = 1
    monkeypatch.setattr("polaris.ui.fastflags.choose", lambda *a, **k: 1)       # 編集を続ける
    win.goto("home"); assert win.current == "editor"
    monkeypatch.setattr("polaris.ui.fastflags.choose", lambda *a, **k: 0)       # 破棄して移動
    win.goto("home"); assert win.current == "home" and win.core.presets.get(c["id"])["flags"] == {"FFlagKeep": 1}


# ---------------- 背景動画 ----------------
def test_video_missing_and_corrupt_do_not_crash(app, tmp_path):
    from polaris.ui.background import BackgroundWidget
    b = BackgroundWidget(); b.resize(320, 180); b.show(); errs = []; b.video_error.connect(errs.append)
    b.configure("video", str(tmp_path / "nothing.mp4"), 30, 40, 50, True); assert b.video_state == "failed" and errs
    bad = tmp_path / "bad.mp4"; bad.write_bytes(b"not a video"); errs.clear()
    b.configure("video", str(bad), 30, 40, 50, True); b.set_active(True)
    assert wait(app, lambda: b.video_state == "failed", 4000) and errs
    b.configure("animated", str(bad), 30, 40, 50, True); b.dispose()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpegが無いためMP4を生成できない")
def test_mp4_play_loop_and_once(app, tmp_path):
    from polaris.ui.background import BackgroundWidget
    mp4 = tmp_path / "t.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x180:rate=15", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    b = BackgroundWidget(); b.resize(320, 180); b.show(); errs = []; b.video_error.connect(errs.append)
    b.configure("video", str(mp4), 30, 40, 50, True); b.set_active(True)
    assert wait(app, lambda: b.video_state == "ok", 5000) and not errs
    QTest.qWait(2200)                                                         # ループ有効: 1秒の動画を超えても再生が続く
    from PySide6.QtMultimedia import QMediaPlayer
    assert b._player.playbackState() == QMediaPlayer.PlayingState and not b._ended
    b.configure("video", str(mp4), 30, 40, 50, False)                          # ループ無効: 最後で停止
    assert wait(app, lambda: b._ended, 5000) and b._player.playbackState() != QMediaPlayer.PlayingState
    b.configure("video", str(mp4), 30, 40, 50, True)                           # ループを戻すと再開
    assert wait(app, lambda: not b._ended and b._player.playbackState() == QMediaPlayer.PlayingState, 4000)
    b.dispose()


def test_worker_shutdown(app, win):
    done = []
    for _ in range(6):
        win.run(lambda: time.sleep(0.05) or 1, lambda r: done.append(r), None)
    assert win.runner.shutdown(3000) and win.runner.pool.activeThreadCount() == 0


def test_window_size_saved_on_close(app, tmp_path):
    RECOVERY_NOTES.clear(); core = make_core(tmp_path); w = MainWindow(core); w.show(); w.resize(1000, 700); app.processEvents(); w.close()
    assert (Core(core.paths).settings.data.win_w, Core(core.paths).settings.data.win_h) == (1000, 700)
