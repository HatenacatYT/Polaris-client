"""GUIテスト（オフスクリーン）。ページ切替の連打・ワーカー終了処理・主要操作。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from polaris.core.app import Core
from polaris.core.paths import AppPaths
from polaris.core.roblox import Detector, PLAYER_EXE
from polaris.ui.theme import apply_theme
from polaris.ui.main_window import MainWindow, PAGES
from polaris.ui.widgets import ANIM
from polaris.ui.dialogs import choose


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    apply_theme(a)
    return a


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    v = tmp_path / "R" / "Versions" / "version-x"; v.mkdir(parents=True); (v / PLAYER_EXE).write_bytes(b"x")
    calls = []
    core = Core(AppPaths(tmp_path / "d"), detector=Detector(roots=[tmp_path / "R" / "Versions"], registry_fn=lambda: None, official_fn=lambda: None),
                launcher_kwargs=dict(open_uri=calls.append, process_running=lambda: True, net_check=lambda: True, sleep=lambda s: None))
    core.settings.data.auto_check_allowlist = False
    from polaris.core.jsonio import RECOVERY_NOTES
    RECOVERY_NOTES.clear()   # 他テストの復旧メモでモーダルが開かないように
    ANIM["on"] = True
    w = MainWindow(core); w.calls = calls; w.show()
    yield w
    w.close()


def wait(app, cond, ms=3000):
    for _ in range(ms // 20):
        app.processEvents()
        if cond():
            return True
        QTest.qWait(20)
    return False


def test_startup_detect_and_pages(app, win):
    assert wait(app, lambda: win.core.last_detection.install is not None)
    assert "検出済み" in win.pages[0].l_status.text()
    assert len(win.pages) == len(PAGES) == 8


@pytest.mark.parametrize("anim", [True, False])
def test_rapid_page_switching(app, win, anim):
    ANIM["on"] = anim
    for i in list(range(8)) * 4 + [3, 1, 5, 0, 7, 2]:
        win.goto(i)
        QTest.qWait(5)
    wait(app, lambda: win.stack._group is None, 1500)
    assert win.stack.currentIndex() == 2 and win.stack.currentWidget().graphicsEffect() is None


def test_sidebar_toggle_and_toast(app, win):
    win.set_collapsed(True); win.set_collapsed(False); win.set_collapsed(True)
    for i in range(8):
        win.toast.show(f"msg{i}", "ok", 100)
    assert len(win.toast.items) <= 4
    wait(app, lambda: not win.toast.items, 2500)
    assert not win.toast.items


def test_add_game_and_flag_and_play(app, win, monkeypatch):
    win.core.games.add("https://www.roblox.com/games/123/x", "テスト")
    win.core.flags.add("FFlagTestOne", True)
    win.refresh_all()
    gp = win.pages[1]
    assert gp.table.rowCount() == 1
    gp.table.selectRow(0); gp._select()
    monkeypatch.setattr("polaris.ui.launch_ui.choose", lambda *a, **k: 0)
    gp.preset.setCurrentIndex(gp.preset.findData(""))
    gp.play(False)
    assert wait(app, lambda: win.calls)
    assert win.calls == ["roblox://experiences/start?placeId=123"]
    assert wait(app, lambda: win.core.games.games[0].launch_count == 1)
    assert wait(app, lambda: "確認できません" in win.pages[0].out.toPlainText())
    fp = win.pages[2]; fp.refresh(); assert fp.table.rowCount() == 1
    fp.table.item(0, 3).setText("false"); app.processEvents()
    assert win.core.flags.flags["FFlagTestOne"].value is False


def test_worker_shutdown(app, win):
    import time
    done = []
    for _ in range(6):
        win.run(lambda: time.sleep(0.05) or 1, lambda r: done.append(r), None)
    assert win.runner.shutdown(3000)
    assert win.runner.pool.activeThreadCount() == 0
