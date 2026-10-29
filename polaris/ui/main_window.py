"""メインウィンドウ（サイドバー、ページ切替、通知、ビジー表示）。"""
from __future__ import annotations
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QButtonGroup, QProgressBar)

from .. import APP_NAME
from ..core.jsonio import RECOVERY_NOTES
from . import assets
from .dialogs import choose
from .launch_ui import LaunchController
from .pages import HomePage, GamesPage, FlagEditorPage, PresetsPage, BackupsPage, LogPage, SettingsPage, AboutPage
from .widgets import ANIM, Sidebar, SlideStack, Spinner, ToastManager, AnimButton
from .workers import TaskRunner

log = logging.getLogger("polaris.ui")
PAGES = [("🏠", "ホーム", HomePage), ("🎮", "ゲームライブラリ", GamesPage), ("🚩", "FastFlagエディター", FlagEditorPage),
         ("📦", "プリセット管理", PresetsPage), ("💾", "バックアップ・復元", BackupsPage), ("📋", "ログ・診断", LogPage),
         ("⚙", "設定", SettingsPage), ("ℹ", "アプリ情報", AboutPage)]


class MainWindow(QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.core = core
        ANIM["on"] = core.settings.data.animations
        self.setWindowTitle(APP_NAME); self.setMinimumSize(980, 640); self.resize(1200, 780)
        self.setWindowIcon(QIcon(str(assets.path("polaris.ico"))))
        self.runner = TaskRunner(self)
        central = QWidget(); self.setCentralWidget(central)
        h = QHBoxLayout(central); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
        self.toast = ToastManager(central)
        self.launch = LaunchController(self)

        # サイドバー
        self.sidebar = Sidebar(); sv = QVBoxLayout(self.sidebar); sv.setContentsMargins(10, 14, 10, 12); sv.setSpacing(4)
        logo = QHBoxLayout(); logo.setSpacing(8)
        self.icon_lbl = QLabel(); self.icon_lbl.setPixmap(QPixmap(str(assets.path("polaris_icon_white.png"))).scaledToHeight(40, Qt.SmoothTransformation))
        self.word_lbl = QLabel(); self.word_lbl.setPixmap(QPixmap(str(assets.path("polaris_wordmark_white.png"))).scaledToHeight(30, Qt.SmoothTransformation))
        logo.addWidget(self.icon_lbl); logo.addWidget(self.word_lbl); logo.addStretch(); sv.addLayout(logo); sv.addSpacing(10)
        self.group = QButtonGroup(self); self.group.setExclusive(True); self.nav = []
        for i, (g, name, _) in enumerate(PAGES):
            b = QPushButton(); b.setObjectName("nav"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor); b.setToolTip(name)
            b.clicked.connect(lambda _=False, i=i: self.goto(i)); self.group.addButton(b, i); sv.addWidget(b); self.nav.append(b)
        sv.addStretch()
        self.toggle = QPushButton("«"); self.toggle.setObjectName("nav"); self.toggle.setToolTip("サイドバーの開閉")
        self.toggle.clicked.connect(lambda: self.set_collapsed(not self.collapsed)); sv.addWidget(self.toggle)
        h.addWidget(self.sidebar)

        # 本体
        right = QWidget(); right.setObjectName("content"); rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(0)
        bar = QHBoxLayout(); bar.setContentsMargins(20, 8, 20, 0)
        self.spin = Spinner(); self.busy_lbl = QLabel(""); self.busy_lbl.setObjectName("muted")
        bar.addStretch(); bar.addWidget(self.busy_lbl); bar.addWidget(self.spin); rv.addLayout(bar)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setTextVisible(False); self.progress.setFixedHeight(4)
        self.progress.setVisible(False); rv.addWidget(self.progress)
        self.stack = SlideStack(); rv.addWidget(self.stack, 1)
        h.addWidget(right, 1)
        self.pages = []
        for _, _, cls in PAGES:
            p = cls(self); self.pages.append(p); self.stack.addWidget(p)
        self.runner.busy_changed.connect(self._busy)
        self.collapsed = False
        self.set_collapsed(core.settings.data.sidebar_collapsed, animate=False)
        self.nav[0].setChecked(True); self.sidebar.hide(); self.refresh_all()
        QTimer.singleShot(250, self._startup)

    # ---- 共通API（ページから使用） ----
    def run(self, fn, on_done=None, on_error=None, *args, label="処理中", **kw):
        self.runner.run(fn, on_done, on_error, *args, label=label, **kw)

    def refresh_all(self):
        for p in self.pages:
            try:
                p.refresh()
            except Exception:  # noqa  1ページの描画失敗でアプリを止めない
                log.exception("page_refresh_error %s", type(p).__name__)

    def set_result(self, text):
        self.pages[0].out.setPlainText(text)

    def apply_home_background(self):
        """ホーム画面に画像またはループ再生動画を設定する。"""
        home = self.pages[0] if self.pages else None
        if home is not None and hasattr(home, "set_background"):
            home.set_background(self.core.settings.data.home_background)

    def goto(self, i):
        self.nav[i].setChecked(True)
        self.sidebar.setVisible(i != 0)
        self.pages[i].refresh()
        self.stack.slide_to(i)

    def redetect(self, after=None):
        def done(_):
            self.refresh_all()
            if after: after()
        self.run(self.core.detect_outcome, done, lambda e: (self.toast.show(f"検出に失敗: {e}", "error"), self.refresh_all()), label="Roblox環境を検出中")

    def set_collapsed(self, c: bool, animate=True):
        self.collapsed = c
        for b, (g, name, _) in zip(self.nav, PAGES):
            b.setText(g if c else f"{g}   {name}")
        self.word_lbl.setVisible(not c); self.toggle.setText("»" if c else "«")
        if animate:
            self.sidebar.set_collapsed(c)
        else:
            self.sidebar._s(Sidebar.COLLAPSED if c else Sidebar.EXPANDED)
        if self.core.settings.data.sidebar_collapsed != c:
            self.core.settings.data.sidebar_collapsed = c
            try: self.core.settings.save()
            except Exception: pass

    def _busy(self, on, label):
        self.progress.setVisible(on); self.busy_lbl.setText(label if on else "")
        self.spin.start() if on else self.spin.stop()

    def resizeEvent(self, e):
        super().resizeEvent(e); self.toast.reflow()

    def _startup(self):
        if RECOVERY_NOTES:
            choose(self, "データを復旧しました", "\n".join(RECOVERY_NOTES) + "\n\n破損したファイルは退避されています。必要なら『バックアップ・復元』から戻せます。", ["OK"], "warn")
            RECOVERY_NOTES.clear()
        self.redetect()
        if self.core.settings.data.auto_check_allowlist and not self.core.allowlist.fresh:
            self.run(self.core.allowlist.refresh_online, lambda n: (self.toast.show(f"公式許可リストを確認しました（{n}件）", "ok"), self.refresh_all()),
                     lambda e: (self.toast.show("公式許可リストを確認できませんでした。フラグは『未確認』扱いになります", "warn", 5000), self.refresh_all()),
                     label="公式許可リストを確認中")

    def closeEvent(self, e):
        log.info("window_close")
        if not self.runner.shutdown(4000):
            log.warning("workers_not_finished")
        self.core.shutdown()
        e.accept()
