import logging
import os
import sys
import traceback


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QPixmap
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
    from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen
    from .core.app import Core
    from .ui.theme import apply_theme
    from .ui.main_window import MainWindow
    from .ui import assets

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Polaris")
    core = Core()
    apply_theme(app, core.settings.data.accent_color)
    log = logging.getLogger("polaris")
    guard = {"busy": False}

    def hook(t, v, tb):  # 予期しない例外でアプリ全体を落とさない
        log.error("unhandled_exception: %s", "".join(traceback.format_exception(t, v, tb)))
        if not guard["busy"]:
            guard["busy"] = True
            try:
                QMessageBox.critical(None, "予期しないエラー", f"{v}\n\n詳細はログ・診断ページで確認できます。操作を続行できます。")
            finally:
                guard["busy"] = False
    sys.excepthook = hook
    # 起動スプラッシュからメインウィンドウへ、実際にサイズが広がる演出。
    # 先に最終位置を決め、メイン画面をスプラッシュと同じ小さな矩形から拡大する。
    from PySide6.QtCore import QRect
    pixmap = QPixmap(str(assets.path("polaris_app.png")))
    if pixmap.isNull():
        pixmap = QPixmap(440, 220)
        pixmap.fill(Qt.black)
    pixmap = pixmap.scaled(440, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.showMessage("Polaris  •  起動中…", Qt.AlignHCenter | Qt.AlignBottom, Qt.white)
    splash.show()
    app.processEvents()

    win = MainWindow(core)
    screen = app.primaryScreen()
    area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
    target_w = min(1200, max(980, area.width() - 80))
    target_h = min(780, max(640, area.height() - 80))
    target = QRect(
        area.x() + (area.width() - target_w) // 2,
        area.y() + (area.height() - target_h) // 2,
        target_w, target_h
    )
    # 小さな開始矩形はスプラッシュの位置を基準にする。
    start = QRect(
        splash.x() + (splash.width() - 440) // 2,
        splash.y() + (splash.height() - 220) // 2,
        440, 220
    )
    win.setGeometry(start)
    win.setWindowOpacity(1.0)

    def reveal():
        # スプラッシュを閉じて、その場所からメインウィンドウを滑らかに拡大。
        splash.close()
        win.show()
        win.raise_()
        win.activateWindow()
        anim = QPropertyAnimation(win, b"geometry", win)
        anim.setDuration(520)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        win._startup_geometry_animation = anim

    # ロゴを最低1秒見せてから拡大を開始。
    QTimer.singleShot(1000, reveal)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
