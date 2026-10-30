"""メインウィンドウ（サイドバー、ページ切替、通知、ビジー表示、言語・外観の再適用）。"""
from __future__ import annotations
import logging

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QIcon, QPixmap, QGuiApplication
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QButtonGroup, QProgressBar,
                               QApplication)

from .. import APP_NAME
from ..core.i18n import N_, tr, set_language
from ..core.jsonio import RECOVERY_NOTES
from . import assets, theme
from .dialogs import choose
from .fastflags import FlagsListPage, PresetEditorPage
from .home import HomePage
from .launch_ui import LaunchController
from .pages import GamesPage, BackupsPage, LogPage, StatusPage
from .settings_page import SettingsPage
from .widgets import ANIM, Sidebar, SlideStack, Spinner, ToastManager
from .workers import TaskRunner

log = logging.getLogger("polaris.ui")
NAV = [("home", "🏠", N_("ホーム")), ("games", "🎮", N_("ゲームライブラリ")), ("flags", "🚩", "FastFlags"),
       ("backups", "💾", N_("バックアップ・復元")), ("logs", "📋", N_("ログ・診断")), ("status", "🖥", N_("Roblox環境")),
       ("settings", "⚙", N_("設定"))]
PAGE_CLASSES = {"home": HomePage, "games": GamesPage, "flags": FlagsListPage, "editor": PresetEditorPage, "backups": BackupsPage,
                "logs": LogPage, "status": StatusPage, "settings": SettingsPage}


class TitleButton(QPushButton):
    """タイトルバーの最小化/最大化/閉じる。ホバーで丸く色が付く。"""
    def __init__(self, glyph, close=False):
        super().__init__(glyph)
        self.close_btn = close
        self.setFixedSize(44, 32); self.setFlat(True); self.setCursor(Qt.ArrowCursor); self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(f"QPushButton{{border:none;border-radius:16px;background:transparent;font-size:12pt;color:{theme.TEXT};}}"
                           f"QPushButton:hover{{background:{'#ff5a74' if close else theme.PANEL2};color:{'white' if close else theme.TEXT};}}"
                           f"QPushButton:pressed{{background:{'#e0435d' if close else theme.BORDER};}}")


class TitleBar(QWidget):
    """枠なしウィンドウ用のタイトルバー。ドラッグで移動、ダブルクリックで最大化。"""
    def __init__(self, win):
        super().__init__()
        self.win = win; self.setObjectName("titlebar"); self.setFixedHeight(42)
        h = QHBoxLayout(self); h.setContentsMargins(14, 0, 8, 0); h.setSpacing(4)
        ic = QLabel(); ic.setPixmap(QPixmap(str(assets.path("polaris_icon_black.png"))).scaledToHeight(22, Qt.SmoothTransformation))
        t = QLabel(APP_NAME); t.setObjectName("h2")
        h.addWidget(ic); h.addSpacing(6); h.addWidget(t); h.addStretch()
        self.busy_lbl = QLabel(""); self.busy_lbl.setObjectName("muted"); self.spin = Spinner(self, 20)
        h.addWidget(self.busy_lbl); h.addWidget(self.spin); h.addSpacing(8)
        self.b_min, self.b_max, self.b_close = TitleButton("–"), TitleButton("□"), TitleButton("✕", True)
        self.b_min.setToolTip(tr("最小化")); self.b_close.setToolTip(tr("閉じる"))
        self.b_min.clicked.connect(win.showMinimized); self.b_max.clicked.connect(win.toggle_max); self.b_close.clicked.connect(win.close)
        for b in (self.b_min, self.b_max, self.b_close):
            h.addWidget(b)
        self.update_max()

    def update_max(self):
        mx = self.win.isMaximized()
        self.b_max.setText("❐" if mx else "□"); self.b_max.setToolTip(tr("元のサイズに戻す") if mx else tr("最大化"))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.win.isMaximized():
            h = self.win.windowHandle()
            if h: h.startSystemMove()       # OS標準の移動（Windowsのスナップにも対応）
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.win.toggle_max()


class Grip(QWidget):
    """ウィンドウ端のリサイズ用グリップ（枠なしのため自前で用意）。"""
    def __init__(self, win, edges, cursor):
        super().__init__(win)
        self.win, self.edges = win, edges
        self.setCursor(cursor); self.setAttribute(Qt.WA_TranslucentBackground)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.win.windowHandle() and not self.win.isMaximized():
            self.win.windowHandle().startSystemResize(self.edges)


class MainWindow(QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.setWindowFlag(Qt.FramelessWindowHint, True)     # 枠なし（独自タイトルバー）
        self.core = core
        s = core.settings.data
        ANIM["on"] = s.animations
        self.setWindowTitle(APP_NAME); self.setMinimumSize(900, 620); self.resize(s.win_w, s.win_h)
        self.setWindowIcon(QIcon(str(assets.path("polaris.ico"))))
        self.runner = TaskRunner(self)
        self.launch = LaunchController(self)
        self.runner.busy_changed.connect(self._busy)
        self.collapsed, self.current, self.last_result_line = s.sidebar_collapsed, None, ""
        self._build_ui()
        self.goto("home", animate=False)
        QTimer.singleShot(250, self._startup)

    # ---- 構築（言語切替時にも再実行する） ----
    def _build_ui(self):
        old = getattr(self, "pages", None)
        if old:
            for k in ("home",):
                old[k].bg.dispose()
            old["settings"].preview.dispose()
        central = QWidget(); central.setObjectName("root")
        outer = QVBoxLayout(central); outer.setContentsMargins(1, 1, 1, 1); outer.setSpacing(0)
        self.titlebar = TitleBar(self); outer.addWidget(self.titlebar)
        body = QWidget(); h = QHBoxLayout(body); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0); outer.addWidget(body, 1)
        self.toast = ToastManager(central)
        self.sidebar = Sidebar(); sv = QVBoxLayout(self.sidebar); sv.setContentsMargins(10, 14, 10, 12); sv.setSpacing(4)
        logo = QHBoxLayout(); logo.setSpacing(8)
        icon = QLabel(); icon.setPixmap(QPixmap(str(assets.path("polaris_icon_black.png"))).scaledToHeight(40, Qt.SmoothTransformation))
        self.word_lbl = QLabel(); self.word_lbl.setPixmap(QPixmap(str(assets.path("polaris_wordmark_black.png"))).scaledToHeight(30, Qt.SmoothTransformation))
        logo.addWidget(icon); logo.addWidget(self.word_lbl); logo.addStretch(); sv.addLayout(logo); sv.addSpacing(10)
        self.group = QButtonGroup(central); self.group.setExclusive(True); self.nav = {}
        for key, glyph, name in NAV:
            b = QPushButton(); b.setObjectName("nav"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor); b.setToolTip(tr(name))
            b.clicked.connect(lambda _=False, k=key: self.goto(k)); self.group.addButton(b); sv.addWidget(b); self.nav[key] = b
        sv.addStretch()
        self.toggle = QPushButton("«"); self.toggle.setObjectName("nav"); self.toggle.setToolTip(tr("サイドバーの開閉"))
        self.toggle.clicked.connect(lambda: self.set_collapsed(not self.collapsed)); sv.addWidget(self.toggle)
        h.addWidget(self.sidebar)
        right = QWidget(); right.setObjectName("content"); rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(0)
        self.spin, self.busy_lbl = self.titlebar.spin, self.titlebar.busy_lbl
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setTextVisible(False); self.progress.setFixedHeight(4)
        self.progress.setVisible(False); rv.addWidget(self.progress)
        self.stack = SlideStack(); rv.addWidget(self.stack, 1); h.addWidget(right, 1)
        self.pages, self.idx = {}, {}
        for name, cls in PAGE_CLASSES.items():
            p = cls(self); self.pages[name] = p; self.idx[name] = self.stack.addWidget(p)
        self.setCentralWidget(central)
        E = Qt.Edge; self.grips = [Grip(self, E.LeftEdge, Qt.SizeHorCursor), Grip(self, E.RightEdge, Qt.SizeHorCursor),
                                   Grip(self, E.TopEdge, Qt.SizeVerCursor), Grip(self, E.BottomEdge, Qt.SizeVerCursor),
                                   Grip(self, E.LeftEdge | E.TopEdge, Qt.SizeFDiagCursor), Grip(self, E.RightEdge | E.BottomEdge, Qt.SizeFDiagCursor),
                                   Grip(self, E.RightEdge | E.TopEdge, Qt.SizeBDiagCursor), Grip(self, E.LeftEdge | E.BottomEdge, Qt.SizeBDiagCursor)]
        self._place_grips()
        self.set_collapsed(self.collapsed, animate=False, save=False)
        self.apply_appearance()
        if self.runner.active_count:
            self._busy(True, tr("処理中"))

    # ---- 共通API ----
    def run(self, fn, on_done=None, on_error=None, *args, label=None, **kw):
        self.runner.run(fn, on_done, on_error, *args, label=label or tr("処理中"), **kw)

    def refresh_all(self):
        for p in self.pages.values():
            try:
                p.refresh()
            except Exception:  # noqa  1ページの描画失敗でアプリを止めない
                log.exception("page_refresh_error %s", type(p).__name__)

    def set_result(self, text):
        self.pages["status"].out.setPlainText(text)
        first = text.strip().split("\n")[0] if text.strip() else ""
        self.last_result_line = (first[:80] + "…") if len(first) > 80 else first
        self.pages["home"].refresh()

    def edit_preset(self, pid):
        if self.pages["editor"].open(pid):
            self.goto("editor")

    def goto(self, name, animate=True):
        if name not in self.pages:
            return
        if self.current == "editor" and name != "editor" and not self.pages["editor"].can_leave():
            self.nav["flags"].setChecked(True); return
        self.current = name
        self.nav["flags" if name == "editor" else name].setChecked(True)
        self.pages[name].refresh()
        self.stack.slide_to(self.idx[name], animate)

    def redetect(self, after=None):
        def done(_):
            self.refresh_all()
            if after: after()
        self.run(self.core.detect_outcome, done, lambda e: (self.toast.show(tr("検出に失敗: {0}", e), "error"), self.refresh_all()),
                 label=tr("Roblox環境を検出中"))

    def apply_bg(self):
        self.pages["home"].apply_appearance()

    def apply_appearance(self):
        theme.set_accent(theme.resolve(self.core.settings.data))
        app = QApplication.instance()
        theme.apply_theme(app)
        self.apply_bg()
        for w in app.allWidgets():
            w.update()

    def change_language(self, code):
        set_language(code)
        QTimer.singleShot(0, self._rebuild)

    def _rebuild(self):
        cur = self.current if self.current != "editor" else "settings"
        self._build_ui(); self.current = None
        self.setWindowTitle(APP_NAME)
        self.goto(cur, animate=False)
        self.redetect()

    def set_collapsed(self, c: bool, animate=True, save=True):
        self.collapsed = c
        for key, glyph, name in NAV:
            self.nav[key].setText(glyph if c else f"{glyph}   {tr(name)}".replace("&", "&&"))   # & はショートカット記号と解釈されるため二重化
        self.word_lbl.setVisible(not c); self.toggle.setText("»" if c else "«")
        if animate:
            self.sidebar.set_collapsed(c)
        else:
            self.sidebar._s(Sidebar.COLLAPSED if c else Sidebar.EXPANDED)
        if save and self.core.settings.data.sidebar_collapsed != c:
            self.core.settings.data.sidebar_collapsed = c
            try: self.core.settings.save()
            except Exception: pass

    def _busy(self, on, label):
        if not hasattr(self, "spin"):
            return
        self.progress.setVisible(on); self.busy_lbl.setText(label if on else "")
        self.spin.start() if on else self.spin.stop()

    def _place_grips(self):
        w, h, g, c = self.width(), self.height(), 5, 12
        rects = [(0, c, g, h - 2 * c), (w - g, c, g, h - 2 * c), (c, 0, w - 2 * c, g), (c, h - g, w - 2 * c, g),
                 (0, 0, c, c), (w - c, h - c, c, c), (w - c, 0, c, c), (0, h - c, c, c)]
        for gr, r in zip(self.grips, rects):
            gr.setGeometry(*r); gr.setVisible(not self.isMaximized()); gr.raise_()

    def toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def resizeEvent(self, e):
        super().resizeEvent(e); self.toast.reflow()
        if hasattr(self, "grips"): self._place_grips()

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange and hasattr(self, "titlebar"):
            self.titlebar.update_max(); self._place_grips()
        if e.type() == QEvent.WindowStateChange and hasattr(self, "pages"):
            self.pages["home"].set_bg_active(not self.isMinimized() and self.current == "home")   # 最小化中は背景を止める
        super().changeEvent(e)

    def _startup(self):
        if RECOVERY_NOTES:
            choose(self, tr("データを復旧しました"), "\n".join(RECOVERY_NOTES) + "\n\n" + tr("破損したファイルは退避されています。必要なら『バックアップ・復元』から戻せます。"), [tr("OK")], "warn")
            RECOVERY_NOTES.clear()
        self.redetect()
        if self.core.settings.data.auto_check_allowlist and not self.core.allowlist.fresh:
            self.run(self.core.allowlist.refresh_online, lambda n: (self.toast.show(tr("公式許可リストを確認しました（{0}件）", n), "ok"), self.refresh_all()),
                     lambda e: (self.toast.show(tr("公式許可リストを確認できませんでした。フラグは『未確認』扱いになります"), "warn", 5000), self.refresh_all()),
                     label=tr("公式許可リストを確認中"))

    def closeEvent(self, e):
        if not self.pages["editor"].can_leave():
            e.ignore(); return
        log.info("window_close")
        if not self.isMaximized() and not self.isFullScreen() and self.isVisible():
            s = self.core.settings.data
            s.win_w, s.win_h = self.width(), self.height()
            try: self.core.settings.save()
            except Exception: log.warning("ウィンドウサイズを保存できません")
        self.pages["home"].bg.dispose(); self.pages["settings"].preview.dispose()
        if not self.runner.shutdown(4000):
            log.warning("workers_not_finished")
        self.core.shutdown()
        e.accept()
