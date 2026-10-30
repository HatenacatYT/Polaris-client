"""ホーム画面: 背景＋右上の歯車＋下部中央（ゲーム名 → プレイ / FastFlags）。"""
from __future__ import annotations
from ..core.i18n import tr, N_
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QBoxLayout, QMenu, QFrame, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor

from .background import BackgroundWidget
from .widgets import AnimButton, GearButton
from .theme import MUTED, OK, WARN, ERR


class HomePage(QWidget):
    title = N_("ホーム")

    def __init__(self, win):
        super().__init__()
        self.win, self.core = win, win.core
        self.bg = BackgroundWidget(self)
        self.bg.video_error.connect(self._bg_error)
        self.content = QWidget(self); self.content.setAttribute(Qt.WA_TranslucentBackground)
        lay = QVBoxLayout(self.content); lay.setContentsMargins(28, 20, 28, 34); lay.setSpacing(10)
        top = QHBoxLayout(); top.addStretch()
        self.gear = GearButton(); self.gear.setToolTip(tr("設定")); self.gear.setAccessibleName(tr("設定"))
        self.gear.clicked.connect(lambda: win.goto("settings")); top.addWidget(self.gear)
        lay.addLayout(top); lay.addStretch(1)

        self.game_btn = AnimButton("", "ghost"); self.game_btn.setMinimumHeight(52)
        f = self.game_btn.font(); f.setPointSize(18); f.setBold(True); self.game_btn.setFont(f)
        self.game_btn.setToolTip(tr("クリックしてゲームを切り替え")); self.game_btn.clicked.connect(self._menu)
        self.info = QLabel(""); self.info.setObjectName("muted"); self.info.setAlignment(Qt.AlignCenter); self.info.setWordWrap(True)
        self.play = AnimButton(tr("▶ プレイ"), "primary"); self.play.setMinimumSize(320, 72)
        f = self.play.font(); f.setPointSize(16); f.setBold(True); self.play.setFont(f); self.play.clicked.connect(self._play)
        self.ff = AnimButton("FastFlags", "secondary"); self.ff.setMinimumSize(180, 72)
        self.ff.setToolTip(tr("FastFlags設定を開く")); self.ff.clicked.connect(lambda: win.goto("flags"))
        self.btn_row = QBoxLayout(QBoxLayout.LeftToRight); self.btn_row.setSpacing(14)
        self.btn_row.addStretch(); self.btn_row.addWidget(self.play); self.btn_row.addWidget(self.ff); self.btn_row.addStretch()
        self.status = QLabel(""); self.status.setAlignment(Qt.AlignCenter); self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        self.gcard = QFrame(); self.gcard.setObjectName("homeCard")
        gv = QVBoxLayout(self.gcard); gv.setContentsMargins(34, 14, 34, 14); gv.setSpacing(2)
        gv.addWidget(self.game_btn, 0, Qt.AlignHCenter); gv.addWidget(self.info, 0, Qt.AlignHCenter)
        sh = QGraphicsDropShadowEffect(self.gcard); sh.setBlurRadius(36); sh.setOffset(0, 8); sh.setColor(QColor(40, 90, 170, 55)); self.gcard.setGraphicsEffect(sh)
        sh2 = QGraphicsDropShadowEffect(self.play); sh2.setBlurRadius(28); sh2.setOffset(0, 8); sh2.setColor(QColor(40, 110, 200, 90)); self.play.setGraphicsEffect(sh2)
        lay.addWidget(self.gcard, 0, Qt.AlignHCenter)
        lay.addLayout(self.btn_row); lay.addWidget(self.status)
        win.launch.busy_changed.connect(self._busy)

    # ---- 背景 ----
    def apply_appearance(self):
        s = self.core.settings.data
        self.bg.configure(s.bg_mode, s.bg_video_path, s.bg_overlay, s.bg_particles, s.bg_speed, s.bg_loop)

    def set_bg_active(self, a: bool):
        self.bg.set_active(a)

    def _bg_error(self, msg):
        self.win.toast.show(msg, "warn", 6000)

    def showEvent(self, e): super().showEvent(e); self.bg.set_active(True)
    def hideEvent(self, e): super().hideEvent(e); self.bg.set_active(False)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.bg.setGeometry(self.rect()); self.content.setGeometry(self.rect())
        # 狭い幅ではボタンを縦に並べ、重ならないようにする
        self.btn_row.setDirection(QBoxLayout.TopToBottom if self.width() < 560 else QBoxLayout.LeftToRight)
        self.play.setMinimumWidth(240 if self.width() < 560 else 320)

    # ---- ゲーム選択・起動 ----
    def _menu(self):
        m = QMenu(self)
        cur = self.core.selected_game()
        for g in self.core.games.games:
            a = m.addAction(("✔ " if cur and g.id == cur.id else "    ") + g.name)
            a.triggered.connect(lambda _=False, gid=g.id: self._select(gid))
        if self.core.games.games:
            m.addSeparator()
        m.addAction(tr("ゲームライブラリを開く…")).triggered.connect(lambda: self.win.goto("games"))
        m.exec(self.game_btn.mapToGlobal(self.game_btn.rect().bottomLeft()))

    def _select(self, gid):
        self.core.select_game(gid); self.refresh()

    def _play(self):
        g = self.core.selected_game()
        if g is None:
            self.win.toast.show(tr("ゲームが登録されていません。ゲームライブラリで追加してください"), "warn", 4500)
            self.win.goto("games"); return
        mode = self.core.settings.data.default_launch_mode
        self.win.launch.start(g, mode if mode in ("apply_and_play", "play_only") else "apply_and_play")

    def _busy(self, b):
        self.play.set_busy(b); self.play.setText(tr("起動中…") if b else tr("▶ プレイ"))

    def refresh(self):
        c, g = self.core, self.core.selected_game()
        if g is None:
            self.game_btn.setText(tr("ゲームが未登録です  ▾")); self.info.setText(tr("ゲームライブラリからPlace IDまたはURLで追加してください"))
        else:
            p = c.active_preset()
            self.game_btn.setText(f"{g.name}  ▾")
            self.info.setText(tr("Place ID {0}  ・  起動 {1} 回  ・  FastFlags: {2}", g.place_id, g.launch_count, p['name'] if p else tr('なし')))
        d = c.last_detection
        if d.install:
            env = f"<span style='color:{OK}'>●</span> Roblox: {d.install.version_name}"
        else:
            env = f"<span style='color:{ERR if d.code != 'NOT_CHECKED' else WARN}'>●</span> Roblox: " + (tr("未検出") if d.code in ("NOT_FOUND", "NOT_CHECKED") else tr("確認できません"))
        last = getattr(self.win, "last_result_line", "")
        self.status.setText(env + (tr("   ｜   {0}", last) if last else ""))
