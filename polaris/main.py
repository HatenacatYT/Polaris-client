import logging
import sys
import time
import traceback

from PySide6.QtCore import Qt, QObject, QTimer, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QSequentialAnimationGroup, \
    QPauseAnimation, Signal
from PySide6.QtGui import QGuiApplication


class Startup(QObject):
    """スプラッシュ表示 → バックグラウンド初期化 → 最低表示時間(1秒) → 拡大しながらメインウィンドウへ移行。"""
    ready = Signal(object)     # 遷移完了後にMainWindowを通知
    failed = Signal(str)

    def __init__(self, app, core_factory=None, min_ms=1000, animate=True):
        super().__init__(app)
        self.app, self.min_ms, self.animate, self.win, self.splash = app, min_ms, animate, None, None
        self.factory = core_factory
        self._done = False

    def start(self):
        from .ui.splash import SplashWindow
        from .ui.workers import TaskRunner
        if self.factory is None:
            from .core.app import Core
            self.factory = Core
        self.t0 = time.monotonic()
        self.splash = SplashWindow(); self.splash.show()
        self.runner = TaskRunner(self)
        self.runner.run(self.factory, self._inited, self._init_failed)
        QTimer.singleShot(8000, lambda: not self._done and self.splash.show_hint("初期化に時間がかかっています… / Initializing is taking longer than usual…"))
        QTimer.singleShot(40000, lambda: not self._done and self._init_failed(TimeoutError("initialization timed out")))

    def _init_failed(self, e):
        if self._done:
            return
        self._done = True
        logging.getLogger("polaris").error("startup_failed: %s", "".join(traceback.format_exception(type(e), e, e.__traceback__)))
        from PySide6.QtWidgets import QMessageBox
        if self.splash: self.splash.close()
        QMessageBox.critical(None, "Polaris", f"Polaris を起動できませんでした。\nFailed to start Polaris.\n\n{e}\n\nログ / Log: %APPDATA%\\Polaris\\logs")
        self.failed.emit(str(e))
        self.app.exit(1)

    def _inited(self, core):
        if self._done:
            return
        self._done = True
        from .core.i18n import set_language
        from .ui import theme
        set_language(core.settings.data.language)
        theme.set_accent(theme.resolve(core.settings.data)); theme.apply_theme(self.app)
        wait = max(0, int(self.min_ms - (time.monotonic() - self.t0) * 1000))   # 初期化が早く終わっても最低表示時間は守る
        QTimer.singleShot(wait, lambda: self._show_main(core))

    def _show_main(self, core):
        from .ui.main_window import MainWindow
        try:
            win = MainWindow(core)
        except Exception as e:  # noqa
            self._done = False; self._init_failed(e); return
        self.win = win
        scr = QGuiApplication.primaryScreen()
        if scr:
            g = scr.availableGeometry(); win.move(g.center().x() - win.width() // 2, g.center().y() - win.height() // 2)
        if not (self.animate and core.settings.data.animations):
            win.show(); self.splash.close(); self.ready.emit(win); return
        win.setWindowOpacity(0.0)      # 表示前に透明化してから表示（白フラッシュ防止）
        win.show()
        target = win.geometry()
        grow = QPropertyAnimation(self.splash, b"geometry"); grow.setDuration(480); grow.setEasingCurve(QEasingCurve.OutCubic)
        grow.setStartValue(self.splash.geometry()); grow.setEndValue(target)
        fin = QSequentialAnimationGroup(); fin.addAnimation(QPauseAnimation(200))
        a = QPropertyAnimation(win, b"windowOpacity"); a.setDuration(260); a.setStartValue(0.0); a.setEndValue(1.0); fin.addAnimation(a)
        fout = QSequentialAnimationGroup(); fout.addAnimation(QPauseAnimation(320))
        b = QPropertyAnimation(self.splash, b"windowOpacity"); b.setDuration(200); b.setStartValue(1.0); b.setEndValue(0.0); fout.addAnimation(b)
        grp = QParallelAnimationGroup(self)
        for x in (grow, fin, fout):
            grp.addAnimation(x)
        grp.finished.connect(lambda: self._finish(win)); self._grp = grp; grp.start()

    def _finish(self, win):
        self.splash.close(); win.setWindowOpacity(1.0); win.activateWindow(); self.ready.emit(win)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from .ui import theme
    from .ui.assets import path as asset

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Polaris")
    theme.apply_theme(app)
    log = logging.getLogger("polaris")
    guard = {"busy": False}

    def hook(t, v, tb):  # 予期しない例外でアプリ全体を落とさない
        log.error("unhandled_exception: %s", "".join(traceback.format_exception(t, v, tb)))
        if not guard["busy"]:
            guard["busy"] = True
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(None, "Polaris", f"{v}\n\nLog page / ログ・診断ページ")
            finally:
                guard["busy"] = False
    sys.excepthook = hook
    st = Startup(app); app._startup = st
    st.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
