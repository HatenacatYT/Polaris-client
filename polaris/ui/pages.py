"""各ページ。すべて refresh() で最新状態を描画する。"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QLineEdit, QComboBox, QTableWidget,
                               QTableWidgetItem, QAbstractItemView, QHeaderView, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QCheckBox, QSpinBox, QFileDialog, QInputDialog, QSplitter, QScrollArea, QColorDialog, QStackedLayout, QSizePolicy)
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from .. import __version__, APP_NAME
from ..core.flags import (CATEGORIES, EDITOR_PRESET_ID, parse_value_text, loads_checked, validate_flags, to_roblox_payload,
                          value_type, validate_flag)
from ..core.jsonio import StorageError, write_json
from ..core.allowlist import AllowlistError
from ..core.backup import RestoreError
from ..core.logsetup import MEMORY
from ..core.roblox import client_settings_path
from ..core.store import AppSettings
from .dialogs import (choose, TextDialog, AddGameDialog, AddFlagDialog, BulkDialog, open_folder, steps_text)
from .theme import MUTED, OK, WARN, ERR
from .widgets import AnimButton, ANIM
from . import assets

log = logging.getLogger("polaris.ui")
UR = Qt.UserRole


def lbl(text="", name=None, wrap=True) -> QLabel:
    l = QLabel(text); l.setWordWrap(wrap)
    if name:
        l.setObjectName(name)
    l.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return l


def card(title="") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame(); f.setObjectName("card")
    v = QVBoxLayout(f); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(8)
    if title:
        v.addWidget(lbl(title, "h2"))
    return f, v


def row(*widgets, stretch=False) -> QHBoxLayout:
    h = QHBoxLayout(); h.setSpacing(8)
    for w in widgets:
        h.addWidget(w)
    if stretch:
        h.addStretch()
    return h


def btn(text, slot, variant="secondary") -> AnimButton:
    b = AnimButton(text, variant); b.clicked.connect(lambda _=False: slot()); return b


def fmt_dt(s: str) -> str:
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return s or "—"


def make_table(headers, widths=None) -> QTableWidget:
    t = QTableWidget(0, len(headers)); t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows); t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False); t.setShowGrid(False)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    for i, w in enumerate(widths or []):
        t.setColumnWidth(i, w)
    return t


class Page(QWidget):
    title = ""

    def __init__(self, win):
        super().__init__()
        self.win, self.core = win, win.core
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame)
        inner = QWidget(); sc.setWidget(inner); outer.addWidget(sc)
        self.root = QVBoxLayout(inner); self.root.setContentsMargins(28, 24, 28, 24); self.root.setSpacing(14)
        self.root.addWidget(lbl(self.title, "h1"))

    def refresh(self): pass


# ───────────────────────── ホーム ─────────────────────────
class HomePage(QWidget):
    """動画を背景に再生し、中央にゲーム起動操作を置くホーム画面。"""
    title = "ホーム"

    def __init__(self, win):
        super().__init__()
        self.win, self.core = win, win.core
        self.setObjectName("PolarisHome")
        self.setMinimumSize(500, 360)
        stack = QStackedLayout(self)
        stack.setStackingMode(QStackedLayout.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)

        # 背景メディア層
        self.bg = QWidget(); self.bg.setObjectName("homeBackground")
        self.bg.setStyleSheet("#homeBackground { background: #090b12; }")
        bgl = QStackedLayout(self.bg); bgl.setStackingMode(QStackedLayout.StackAll); bgl.setContentsMargins(0,0,0,0)
        self.bg_image = QLabel(); self.bg_image.setAlignment(Qt.AlignCenter); self.bg_image.setScaledContents(False)
        self.bg_image.setStyleSheet("background: #090b12;")
        self.video = QVideoWidget(); self.video.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)
        bgl.addWidget(self.bg_image); bgl.addWidget(self.video)
        stack.addWidget(self.bg)

        self.player = QMediaPlayer(self); self.audio = QAudioOutput(self)
        self.audio.setVolume(0.0); self.player.setAudioOutput(self.audio); self.player.setVideoOutput(self.video)
        self.player.mediaStatusChanged.connect(self._media_status)
        self._video_path = ""
        self._background_path = None

        # UI層：上部の設定ボタン、中央のゲーム選択と起動ボタン
        overlay = QWidget(); overlay.setObjectName("homeOverlay")
        overlay.setStyleSheet("#homeOverlay { background: transparent; }")
        outer = QVBoxLayout(overlay); outer.setContentsMargins(30,24,30,28); outer.setSpacing(0)
        top = QHBoxLayout(); top.setSpacing(8)
        brand = QLabel("✦  POLARIS"); brand.setStyleSheet("font-size:18px;font-weight:800;letter-spacing:3px;color:white;background:transparent;")
        top.addWidget(brand); top.addStretch()
        self.gear = btn("⚙", lambda: self.win.goto(6)); self.gear.setToolTip("設定"); self.gear.setFixedSize(44,44)
        top.addWidget(self.gear); outer.addLayout(top)
        outer.addStretch(4)
        center = QVBoxLayout(); center.setAlignment(Qt.AlignHCenter); center.setSpacing(14)
        eyebrow = QLabel("YOUR ROBLOX HUB"); eyebrow.setAlignment(Qt.AlignCenter)
        eyebrow.setStyleSheet("color:#c5c9d7;font-size:11px;font-weight:700;letter-spacing:4px;background:transparent;")
        center.addWidget(eyebrow)
        title = QLabel("Polaris"); title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:white;font-size:48px;font-weight:800;background:transparent;")
        center.addWidget(title)
        subtitle = QLabel("ゲームを選択して、冒険を始めよう。"); subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#e1e4ed;font-size:14px;background:transparent;")
        center.addWidget(subtitle)
        self.game_combo = QComboBox(); self.game_combo.setMinimumWidth(300); self.game_combo.setMinimumHeight(44)
        self.game_combo.setStyleSheet("QComboBox { background:rgba(17,20,31,220); color:white; border:1px solid rgba(255,255,255,90); border-radius:10px; padding:8px 14px; font-size:14px; } QComboBox QAbstractItemView { background:#171a25; color:white; selection-background-color:#7c5cff; }")
        center.addWidget(self.game_combo, 0, Qt.AlignHCenter)
        self.play_button = btn("▶   プレイ", lambda: self.play(True), "primary")
        self.play_button.setMinimumSize(300,54); self.play_button.setStyleSheet(self.play_button.styleSheet() + "\nQPushButton { font-size:16px; font-weight:700; border-radius:12px; }")
        center.addWidget(self.play_button, 0, Qt.AlignHCenter)
        actions = QHBoxLayout(); actions.setSpacing(10)
        self.flags_button = btn("⚑  FastFlags", lambda: self.win.goto(2))
        self.library_button = btn("▦  ゲームライブラリ", lambda: self.win.goto(1))
        actions.addWidget(self.flags_button); actions.addWidget(self.library_button)
        center.addLayout(actions)
        self.status = QLabel("Robloxの状態を確認しています…"); self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color:#d4d7e0;font-size:12px;background:transparent;")
        center.addWidget(self.status)
        outer.addLayout(center); outer.addStretch(5)
        bottom = QHBoxLayout()
        self.footer = QLabel("POLARIS  •  CUSTOM ROBLOX LAUNCHER")
        self.footer.setStyleSheet("color:rgba(255,255,255,150);font-size:10px;letter-spacing:2px;background:transparent;")
        bottom.addWidget(self.footer); bottom.addStretch()
        self.diag_button = btn("診断情報", self.show_diag); bottom.addWidget(self.diag_button)
        outer.addLayout(bottom)
        stack.addWidget(overlay)
        stack.setCurrentWidget(overlay)
        self._overlay = overlay
        self._image = QPixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._image.isNull() and self.bg_image.isVisible():
            self._set_cover_image()

    def _set_cover_image(self):
        if self._image.isNull(): return
        scaled = self._image.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width()-self.width())//2); y = max(0,(scaled.height()-self.height())//2)
        self.bg_image.setPixmap(scaled.copy(x,y,self.width(),self.height()))

    def set_background(self, path=""):
        from pathlib import Path
        path = str(path or "")
        if path == self._background_path and path and Path(path).is_file():
            if Path(path).suffix.lower() in (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm") and self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.player.play()
            return
        self._background_path = path
        self.player.stop(); self._video_path = ""; self._image = QPixmap()
        p = Path(path) if path else None
        if p and p.is_file() and p.suffix.lower() in (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"):
            self.bg_image.hide(); self.video.show(); self._video_path = str(p.resolve())
            self.player.setSource(QUrl.fromLocalFile(self._video_path)); self.player.play()
        elif p and p.is_file():
            self._image = QPixmap(str(p)); self.video.hide(); self.bg_image.show(); self._set_cover_image()
        else:
            self.video.hide(); self.bg_image.show(); self.bg_image.clear(); self.bg_image.setStyleSheet("background:#090b12;")

    def _media_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.EndOfMedia and self._video_path:
            self.player.setPosition(0); self.player.play()

    def selected_game(self):
        game_id = self.game_combo.currentData()
        return self.core.games.get(game_id) if game_id else None

    def play(self, apply=True):
        game = self.selected_game()
        if game is None:
            self.win.toast.show("ゲームがありません。ゲームライブラリから追加してください。", "warn"); return
        self.win.launch.start(game, "apply_and_play" if apply else "play_only")

    def apply_only(self):
        self.win.launch.start(None, "apply_only", self.core.settings.data.active_preset)

    def roblox_only(self):
        self.win.launch.start(None, "roblox_only")

    def show_diag(self):
        TextDialog(self.win, "診断情報", "個人情報・認証情報はマスクされています。", self.core.diagnostics_text()).exec()

    def refresh(self):
        self.game_combo.blockSignals(True); current = self.game_combo.currentData(); self.game_combo.clear()
        games = self.core.games.search("") if hasattr(self.core.games, "search") else []
        if not games:
            # GameStoreの公開一覧API名に依存しないよう、最近/お気に入りから候補を集める。
            seen = {}
            for g in list(self.core.games.recent(100)) + list(self.core.games.favorites()): seen[g.id] = g
            games = list(seen.values())
        for g in games: self.game_combo.addItem(g.name, g.id)
        idx = self.game_combo.findData(current)
        if idx >= 0: self.game_combo.setCurrentIndex(idx)
        self.game_combo.blockSignals(False)
        d = self.core.last_detection
        self.status.setText(("● Roblox 検出済み" if d.install else "● Roblox 未検出") + "   •   " + self.core.allowlist.state_text())
        self.set_background(self.core.settings.data.home_background)



# ───────────────────────── ゲームライブラリ ─────────────────────────
class GamesPage(Page):
    title = "ゲームライブラリ"

    def __init__(self, win):
        super().__init__(win)
        self.cur = None
        top = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("ゲーム名・Place IDで検索"); self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search, 1); top.addWidget(btn("＋ ゲームを追加", self.add, "primary")); self.root.addLayout(top)
        sp = QSplitter(); self.root.addWidget(sp, 1)
        self.table = make_table(["★", "ゲーム名", "Place ID", "起動回数", "最終起動"], [44, 240, 120, 80, 150])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self._select); self.table.cellDoubleClicked.connect(lambda *_: self.play(self.core.settings.data.default_launch_mode == "apply_and_play"))
        self.table.setMinimumHeight(320)
        sp.addWidget(self.table)
        f, v = card("詳細")
        self.name, self.pid = QLineEdit(), QLineEdit()
        self.note = QPlainTextEdit(); self.note.setPlaceholderText("メモ"); self.note.setMaximumHeight(90)
        self.preset = QComboBox()
        self.fav = QCheckBox("お気に入り"); self.apply_cb = QCheckBox("起動時にFastFlagを適用する"); self.verify_cb = QCheckBox("起動後にRobloxプロセスを確認する")
        for t, w in (("ゲーム名", self.name), ("Place ID", self.pid), ("メモ", self.note), ("FastFlagプリセット", self.preset)):
            v.addWidget(lbl(t, "muted")); v.addWidget(w)
        for w in (self.fav, self.apply_cb, self.verify_cb):
            v.addWidget(w)
        v.addLayout(row(btn("保存", self.save, "primary"), btn("削除", self.delete, "danger"), stretch=True))
        v.addLayout(row(btn("▶ プレイ（設定を適用）", lambda: self.play(True), "primary"), btn("設定なしで起動", lambda: self.play(False)), stretch=True))
        sp.addWidget(f); sp.setStretchFactor(0, 3); sp.setStretchFactor(1, 2)
        self._set_form(None)

    def _games(self): return self.core.games.search(self.search.text())

    def refresh(self):
        keep = self.cur
        self.table.blockSignals(True); self.table.setRowCount(0)
        for g in self._games():
            r = self.table.rowCount(); self.table.insertRow(r)
            vals = ["★" if g.favorite else "", g.name, str(g.place_id), str(g.launch_count), fmt_dt(g.last_launched) if g.last_launched else "—"]
            for c, t in enumerate(vals):
                it = QTableWidgetItem(t); it.setData(UR, g.id); self.table.setItem(r, c, it)
            if g.id == keep:
                self.table.selectRow(r)
        self.table.blockSignals(False)
        self.preset.clear()
        self.preset.addItem("（ホームで選択中のプリセットを使う）", "")
        for pid, name in self.core.preset_choices()[1:]:
            self.preset.addItem(name, pid)
        self._select()

    def _select(self):
        rows = self.table.selectionModel().selectedRows()
        self.cur = self.table.item(rows[0].row(), 0).data(UR) if rows else None
        self._set_form(self.core.games.get(self.cur) if self.cur else None)

    def _set_form(self, g):
        en = g is not None
        for w in (self.name, self.pid, self.note, self.preset, self.fav, self.apply_cb, self.verify_cb):
            w.setEnabled(en)
        if not en:
            self.name.clear(); self.pid.clear(); self.note.clear(); return
        self.name.setText(g.name); self.pid.setText(str(g.place_id)); self.note.setPlainText(g.note)
        self.fav.setChecked(g.favorite); self.apply_cb.setChecked(g.apply_flags); self.verify_cb.setChecked(g.verify_process)
        self.preset.setCurrentIndex(max(0, self.preset.findData(g.preset_id)))

    def add(self):
        d = AddGameDialog(self.win)
        if d.exec():
            try:
                g = self.core.games.add(*d.values())
                self.cur = g.id; self.win.toast.show(f"『{g.name}』を追加しました", "ok"); self.win.refresh_all()
            except (ValueError, StorageError) as e:
                choose(self.win, "追加できません", str(e), ["閉じる"], "error")

    def save(self):
        if not self.cur:
            return
        try:
            from ..core.games import parse_place_input
            self.core.games.update(self.cur, name=self.name.text(), place_id=parse_place_input(self.pid.text()),
                                   note=self.note.toPlainText(), favorite=self.fav.isChecked(), apply_flags=self.apply_cb.isChecked(),
                                   verify_process=self.verify_cb.isChecked(), preset_id=self.preset.currentData() or "")
            self.win.toast.show("保存しました", "ok"); self.win.refresh_all()
        except (ValueError, StorageError) as e:
            choose(self.win, "保存できません", str(e), ["閉じる"], "error")

    def delete(self):
        g = self.core.games.get(self.cur) if self.cur else None
        if g and choose(self.win, "ゲームの削除", f"『{g.name}』をライブラリから削除しますか？（Robloxのデータには影響しません）", ["削除", "キャンセル"], "warn") == 0:
            self.core.games.delete(g.id); self.cur = None; self.win.refresh_all(); self.win.toast.show("削除しました", "ok")

    def play(self, apply: bool):
        g = self.core.games.get(self.cur) if self.cur else None
        if g is None:
            self.win.toast.show("ゲームを選択してください", "warn"); return
        self.save()
        self.win.launch.start(g, "apply_and_play" if apply else "play_only")


# ───────────────────────── FastFlagエディター ─────────────────────────
class FlagEditorPage(Page):
    title = "FastFlagエディター"
    COLS = ["有効", "★", "フラグ名", "値", "型", "カテゴリ", "公式許可リスト"]
    STAT = {"allowed": "公式掲載", "not_listed": "未掲載（無視される可能性）", "unverified": "未確認（リスト未取得/期限切れ）"}

    def __init__(self, win):
        super().__init__(win)
        self._loading = False
        self.info = lbl(name="muted"); self.root.addWidget(self.info)
        r1 = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("フラグ名・値・メモで検索"); self.search.textChanged.connect(self.refresh)
        self.cat = QComboBox(); self.cat.addItems(["すべてのカテゴリ"] + CATEGORIES); self.cat.currentIndexChanged.connect(self.refresh)
        self.flt = QComboBox(); self.flt.addItems(["すべて", "お気に入り", "有効のみ", "公式掲載のみ", "公式未掲載/未確認"]); self.flt.currentIndexChanged.connect(self.refresh)
        r1.addWidget(self.search, 1); r1.addWidget(self.cat); r1.addWidget(self.flt); self.root.addLayout(r1)
        self.root.addLayout(row(btn("＋ 追加", self.add, "primary"), btn("一括編集", self.bulk), btn("削除", self.delete, "danger"),
                                btn("インポート", self.import_), btn("エクスポート", self.export), btn("検証", self.validate), stretch=True))
        self.root.addLayout(row(btn("公式リストを更新", self.update_allow), btn("許可リストをファイルから読込", self.load_allow),
                                btn("▶ エディターの設定をRobloxへ適用", self.apply, "primary"), stretch=True))
        self.table = make_table(self.COLS, [56, 44, 300, 160, 70, 130, 230])
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection); self.table.setMinimumHeight(360)
        self.table.itemChanged.connect(self._changed)
        self.root.addWidget(self.table, 1)

    def _rows(self):
        q, cat, f, al = self.search.text().lower().strip(), self.cat.currentText(), self.flt.currentIndex(), self.core.allowlist
        for fl in self.core.flags.flags.values():
            if q and q not in fl.name.lower() and q not in str(fl.value).lower() and q not in fl.note.lower():
                continue
            if self.cat.currentIndex() > 0 and fl.category != cat: continue
            st = al.status(fl.name)
            if f == 1 and not fl.favorite: continue
            if f == 2 and not fl.enabled: continue
            if f == 3 and st != "allowed": continue
            if f == 4 and st == "allowed": continue
            yield fl, st

    def refresh(self):
        self._loading = True
        self.info.setText("公式許可リスト: " + self.core.allowlist.state_text() +
                          "\n公式リストに無いフラグはRobloxに無視されます（ペナルティはありません）。書き込み成功≠ゲーム内での反映です。")
        self.table.setRowCount(0)
        for fl, st in self._rows():
            r = self.table.rowCount(); self.table.insertRow(r)
            def mk(text, editable=False, check=None):
                it = QTableWidgetItem(text); it.setData(UR, fl.name)
                fl_ = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if editable: fl_ |= Qt.ItemIsEditable
                if check is not None: fl_ |= Qt.ItemIsUserCheckable; it.setCheckState(Qt.Checked if check else Qt.Unchecked)
                it.setFlags(fl_); return it
            val = json.dumps(fl.value, ensure_ascii=False)
            for c, it in enumerate([mk("", check=fl.enabled), mk("", check=fl.favorite), mk(fl.name, True), mk(val, True),
                                    mk(value_type(fl.value)), mk(fl.category), mk(self.STAT[st])]):
                self.table.setItem(r, c, it)
        self._loading = False

    def _changed(self, item):
        if self._loading:
            return
        name, col, fs = item.data(UR), item.column(), self.core.flags
        try:
            if col == 0: fs.set_attr([name], enabled=item.checkState() == Qt.Checked)
            elif col == 1: fs.set_attr([name], favorite=item.checkState() == Qt.Checked)
            elif col == 2: fs.rename(name, item.text())
            elif col == 3: fs.update_value(name, parse_value_text(item.text()))
        except (ValueError, KeyError, StorageError) as e:
            self.win.toast.show(f"変更できません: {e}", "error", 5000)
        QTimer.singleShot(0, self.refresh)

    def _selected(self):
        return sorted({self.table.item(i.row(), 2).data(UR) for i in self.table.selectionModel().selectedRows()})

    def add(self):
        d = AddFlagDialog(self.win, self.core.allowlist.status)
        if d.exec():
            n, v, c, note = d.values()
            try:
                self.core.flags.add(n, v, c, note)
                st = self.core.allowlist.status(n)
                self.win.toast.show("追加しました" + ("" if st == "allowed" else "（公式リストで確認できないため、反映されない可能性があります）"), "ok" if st == "allowed" else "warn", 4500)
                self.win.refresh_all()
            except (ValueError, StorageError) as e:
                choose(self.win, "追加できません", str(e), ["閉じる"], "error")

    def delete(self):
        names = self._selected()
        if names and choose(self.win, "削除", f"{len(names)}件のフラグを削除しますか？", ["削除", "キャンセル"], "warn") == 0:
            self.core.flags.delete(names); self.win.refresh_all()

    def bulk(self):
        names = self._selected()
        if not names:
            self.win.toast.show("対象の行を選択してください", "warn"); return
        d = BulkDialog(self.win, len(names))
        if not d.exec():
            return
        a, fs = d.act.currentIndex(), self.core.flags
        try:
            if a == 0: fs.set_attr(names, enabled=True)
            elif a == 1: fs.set_attr(names, enabled=False)
            elif a == 2: fs.set_attr(names, favorite=True)
            elif a == 3: fs.set_attr(names, favorite=False)
            elif a == 4: fs.set_attr(names, category=d.cat.currentText())
            elif a == 5:
                if choose(self.win, "削除", f"{len(names)}件を削除しますか？", ["削除", "キャンセル"], "warn") == 0: fs.delete(names)
            self.win.toast.show("一括編集を反映しました", "ok"); self.win.refresh_all()
        except StorageError as e:
            choose(self.win, "保存できません", str(e), ["閉じる"], "error")

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self.win, "FastFlag JSONを選択", "", "JSON (*.json);;すべて (*)")
        if not path:
            return
        try:
            text = Path(path).read_text("utf-8-sig")
        except (OSError, UnicodeDecodeError) as e:
            choose(self.win, "読み込めません", str(e), ["閉じる"], "error"); return
        data, dups, errs = loads_checked(text)
        log.info("flags_json_validated errors=%d dups=%d", len(errs), len(dups))
        if data is None or errs:
            TextDialog(self.win, "インポートできません", "JSONの検証でエラーが見つかりました。修正してから再度インポートしてください。", "\n".join(errs[:50])).exec(); return
        msg = f"{len(data)}件のフラグを読み込みます。"
        if dups:
            msg += f"\n⚠ 重複キー（後の値を採用）: {', '.join(dups[:10])}"
        i = choose(self.win, "インポート", msg, ["既存に追加/更新", "すべて置き換え", "キャンセル"], "question")
        if i < 2:
            try:
                a, u = self.core.flags.import_flags(data, overwrite=(i == 1))
                self.win.toast.show(f"追加 {a} / 更新 {u} 件", "ok"); self.win.refresh_all()
            except StorageError as e:
                choose(self.win, "保存できません", str(e), ["閉じる"], "error")

    def export(self):
        i = choose(self.win, "エクスポート", "形式を選択してください。", ["Roblox形式（有効なフラグのみ）", "Polaris形式（全項目）", "キャンセル"])
        if i == 2:
            return
        path, _ = QFileDialog.getSaveFileName(self.win, "保存先", "ClientAppSettings.json" if i == 0 else "polaris_flags.json", "JSON (*.json)")
        if not path:
            return
        try:
            if i == 0:
                write_json(path, to_roblox_payload(self.core.flags.enabled_dict(), self.core.settings.data.value_format), keep_bak=False)
            else:
                from dataclasses import asdict
                write_json(path, {"flags": [asdict(f) for f in self.core.flags.flags.values()]}, keep_bak=False)
            self.win.toast.show("エクスポートしました", "ok")
        except StorageError as e:
            choose(self.win, "保存できません", str(e), ["閉じる"], "error")

    def validate(self):
        fl = self.core.flags.flags
        errs = validate_flags({k: v.value for k, v in fl.items()})
        st = [self.core.allowlist.status(n) for n in self.core.flags.enabled_dict()]
        body = "\n".join(errs) if errs else "形式エラーはありません。"
        body += f"\n\n有効なフラグ: {len(st)}件 ／ 公式掲載 {st.count('allowed')} ／ 未掲載 {st.count('not_listed')} ／ 未確認 {st.count('unverified')}"
        body += "\n（フラグ名の重複はエディター上では登録できません。インポート時に重複キーを検出します）"
        TextDialog(self.win, "検証結果", "FastFlagの検証結果", body).exec()

    def update_allow(self):
        self.win.run(self.core.allowlist.refresh_online, self._allow_ok, self._allow_err, label="公式許可リストを取得中")

    def _allow_ok(self, n):
        self.win.toast.show(f"公式リストを更新しました（{n}件・自動抽出のため要目視確認）", "ok", 4500); self.win.refresh_all()

    def _allow_err(self, e):
        self.win.toast.show(f"{e}", "error", 6000); self.win.refresh_all()

    def load_allow(self):
        path, _ = QFileDialog.getOpenFileName(self.win, "許可リストのテキスト/JSON", "", "テキスト/JSON (*.txt *.json *.md);;すべて (*)")
        if path:
            try:
                n = self.core.allowlist.import_text(Path(path).read_text("utf-8-sig"), Path(path).name)
                self.win.toast.show(f"{n}件を読み込みました（ユーザー提供ファイル）", "ok"); self.win.refresh_all()
            except (AllowlistError, OSError, UnicodeDecodeError) as e:
                self.win.toast.show(str(e), "error", 5000)

    def apply(self):
        self.win.launch.start(None, "apply_only", EDITOR_PRESET_ID)


# ───────────────────────── プリセット管理 ─────────────────────────
class PresetsPage(Page):
    title = "プリセット管理"

    def __init__(self, win):
        super().__init__(win)
        self.cur = None
        sp = QSplitter(); self.root.addWidget(sp, 1)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        self.lst = QListWidget(); self.lst.setMinimumHeight(300); self.lst.currentItemChanged.connect(self._sel); lv.addWidget(self.lst)
        lv.addLayout(row(btn("新規（空）", self.new, "primary"), btn("エディターから作成", self.from_editor), stretch=True))
        lv.addLayout(row(btn("複製", self.dup), btn("削除", self.delete, "danger"), btn("インポート", self.import_), stretch=True))
        sp.addWidget(left)
        f, v = card("プリセットの内容")
        self.name = QLineEdit(); self.cat = QComboBox(); self.cat.addItems(CATEGORIES)
        self.js = QPlainTextEdit(); self.js.setPlaceholderText('{ "FFlagExample": true, "FIntExample": 5 }'); self.js.setMinimumHeight(200)
        v.addWidget(lbl("名前", "muted")); v.addWidget(self.name); v.addWidget(lbl("カテゴリ", "muted")); v.addWidget(self.cat)
        v.addWidget(lbl("フラグ（JSON。効果は未検証であり、性能向上を保証するものではありません）", "muted")); v.addWidget(self.js, 1)
        v.addLayout(row(btn("検証して保存", self.save, "primary"), btn("エディターへ読み込み", self.to_editor), btn("エクスポート", self.export), stretch=True))
        sp.addWidget(f); sp.setStretchFactor(0, 2); sp.setStretchFactor(1, 3)
        self._form(None)

    def refresh(self):
        keep = self.cur
        self.lst.blockSignals(True); self.lst.clear()
        for p in self.core.presets.presets:
            it = QListWidgetItem(f"{p['name']}　［{p['category']}］ {len(p['flags'])}件"); it.setData(UR, p["id"]); self.lst.addItem(it)
            if p["id"] == keep: self.lst.setCurrentItem(it)
        self.lst.blockSignals(False)
        self._sel()

    def _sel(self, *_):
        it = self.lst.currentItem()
        self.cur = it.data(UR) if it else None
        self._form(self.core.presets.get(self.cur) if self.cur else None)

    def _form(self, p):
        for w in (self.name, self.cat, self.js):
            w.setEnabled(p is not None)
        if p is None:
            self.name.clear(); self.js.clear(); return
        self.name.setText(p["name"]); self.cat.setCurrentText(p["category"])
        self.js.setPlainText(json.dumps(p["flags"], ensure_ascii=False, indent=2))

    def _guard(self, fn):
        try:
            return fn()
        except (ValueError, KeyError, StorageError) as e:
            choose(self.win, "処理できません", str(e), ["閉じる"], "error")

    def new(self):
        name, ok = QInputDialog.getText(self.win, "新規プリセット", "プリセット名:")
        if ok and self._guard(lambda: self._mk(name, {})): self.win.refresh_all()

    def _mk(self, name, flags):
        p = self.core.presets.create(name, "その他", flags); self.cur = p["id"]; return True

    def from_editor(self):
        flags = self.core.flags.enabled_dict()
        if not flags:
            self.win.toast.show("エディターに有効なフラグがありません", "warn"); return
        name, ok = QInputDialog.getText(self.win, "エディターから作成", f"{len(flags)}件の有効フラグを保存します。プリセット名:")
        if ok and self._guard(lambda: self._mk(name, flags)): self.win.refresh_all(); self.win.toast.show("作成しました", "ok")

    def dup(self):
        if self.cur and self._guard(lambda: setattr(self, "cur", self.core.presets.duplicate(self.cur)["id"]) or True):
            self.win.refresh_all(); self.win.toast.show("複製しました", "ok")

    def delete(self):
        p = self.core.presets.get(self.cur) if self.cur else None
        if p and choose(self.win, "削除", f"プリセット『{p['name']}』を削除しますか？", ["削除", "キャンセル"], "warn") == 0:
            self.core.presets.delete(p["id"]); self.cur = None
            if self.core.settings.data.active_preset == p["id"]:
                self.core.settings.data.active_preset = ""; self.core.settings.save()
            self.win.refresh_all()

    def save(self):
        if not self.cur:
            return
        data, dups, errs = loads_checked(self.js.toPlainText() or "{}")
        if data is None or errs:
            TextDialog(self.win, "検証エラー", "JSONを修正してください。", "\n".join(errs[:50])).exec(); return
        if dups:
            self.win.toast.show(f"重複キー（後の値を採用）: {', '.join(dups[:5])}", "warn", 5000)
        if self._guard(lambda: self.core.presets.update(self.cur, name=self.name.text(), category=self.cat.currentText(), flags=data) or True):
            self.win.toast.show("プリセットを保存しました", "ok"); self.win.refresh_all()

    def to_editor(self):
        p = self.core.presets.get(self.cur) if self.cur else None
        if not p:
            return
        i = choose(self.win, "エディターへ読み込み", f"『{p['name']}』の{len(p['flags'])}件をエディターへ読み込みます。", ["既存に追加/更新", "すべて置き換え", "キャンセル"])
        if i < 2 and self._guard(lambda: self.core.flags.import_flags(p["flags"], overwrite=(i == 1)) and True):
            self.win.toast.show("読み込みました", "ok"); self.win.refresh_all()

    def export(self):
        p = self.core.presets.get(self.cur) if self.cur else None
        if p:
            path, _ = QFileDialog.getSaveFileName(self.win, "保存先", f"{p['name']}.json", "JSON (*.json)")
            if path and self._guard(lambda: write_json(path, p, keep_bak=False) or True):
                self.win.toast.show("エクスポートしました", "ok")

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self.win, "プリセットJSON", "", "JSON (*.json)")
        if not path:
            return
        try:
            data, dups, errs = loads_checked(Path(path).read_text("utf-8-sig"))
        except (OSError, UnicodeDecodeError) as e:
            choose(self.win, "読み込めません", str(e), ["閉じる"], "error"); return
        if data is None:
            TextDialog(self.win, "検証エラー", "JSONを読み込めません。", "\n".join(errs)).exec(); return
        name, cat, flags = Path(path).stem, "その他", data
        if isinstance(data.get("flags"), dict) and isinstance(data.get("name"), str):
            name, cat, flags = data["name"], data.get("category", "その他"), data["flags"]
        errs = validate_flags(flags)
        if errs:
            TextDialog(self.win, "検証エラー", "フラグに問題があります。", "\n".join(errs[:50])).exec(); return
        if self._guard(lambda: self.core.presets.create(name, cat, flags) and True):
            self.win.refresh_all(); self.win.toast.show("インポートしました", "ok")


# ───────────────────────── バックアップ・復元 ─────────────────────────
class BackupsPage(Page):
    title = "バックアップ・復元"

    def __init__(self, win):
        super().__init__(win)
        self.dir_lbl = lbl(name="muted"); self.root.addWidget(self.dir_lbl)
        self.root.addLayout(row(btn("Roblox設定をバックアップ", self.bk_roblox), btn("アプリデータをバックアップ", self.bk_app),
                                btn("保存先を変更", self.set_dir), btn("保存先を既定に戻す", self.reset_dir), btn("フォルダを開く", lambda: open_folder(self.core.backup_dir())), stretch=True))
        self.table = make_table(["日時", "種別", "内容", "対象パス"], [170, 100, 220, 400])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setSelectionMode(QAbstractItemView.SingleSelection); self.table.setMinimumHeight(280)
        self.root.addWidget(self.table, 1)
        self.root.addLayout(row(btn("選択したバックアップから復元", self.restore, "primary"), btn("選択を削除", self.delete, "danger"), stretch=True))
        f, v = card("自動削除（既定ではオフ。ユーザーの同意なしに削除しません）")
        self.auto = QCheckBox("バックアップ作成後、古いものを自動削除する")
        self.mx, self.days = QSpinBox(), QSpinBox()
        self.mx.setRange(1, 10000); self.days.setRange(0, 36500); self.days.setSpecialValueText("無期限")
        v.addWidget(self.auto)
        v.addLayout(row(lbl("最大保存数"), self.mx, lbl("保存期間(日)"), self.days, btn("今すぐ整理", self.prune_now), stretch=True))
        for w, sig in ((self.auto, self.auto.toggled), (self.mx, self.mx.valueChanged), (self.days, self.days.valueChanged)):
            sig.connect(self._save_prune)
        self.root.addWidget(f)
        self._loading = False

    def _entries(self): return self.core.backups.list()

    def refresh(self):
        s = self.core.settings.data
        self._loading = True
        self.auto.setChecked(s.backup_auto_prune); self.mx.setValue(s.backup_max_count); self.days.setValue(s.backup_max_days)
        self._loading = False
        self.dir_lbl.setText(f"保存先: {self.core.backup_dir()}")
        self.table.setRowCount(0)
        for e in self._entries():
            r = self.table.rowCount(); self.table.insertRow(r)
            for c, t in enumerate([fmt_dt(e.created_at), e.kind, e.label, " / ".join(m["source"] for m in e.files)]):
                it = QTableWidgetItem(t); it.setData(UR, e.id); self.table.setItem(r, c, it)

    def _sel(self):
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).data(UR) if rows else None

    def _save_prune(self, *_):
        if self._loading: return
        s = self.core.settings.data
        s.backup_auto_prune, s.backup_max_count, s.backup_max_days = self.auto.isChecked(), self.mx.value(), self.days.value()
        self._try(self.core.settings.save)

    def _try(self, fn):
        try:
            return fn(), True
        except (StorageError, OSError) as e:
            choose(self.win, "失敗しました", str(e), ["閉じる"], "error"); return None, False

    def bk_roblox(self):
        def job():
            d = self.core.detect_outcome()
            if d.install is None: raise StorageError(d.message)
            return self.core.backups.create("roblox", "手動バックアップ", [client_settings_path(d.install)])
        self.win.run(job, lambda e: (self.win.toast.show("バックアップしました", "ok"), self.win.refresh_all()),
                     lambda e: choose(self.win, "バックアップできません", f"{e}\n（ClientAppSettings.json が存在しない場合は対象がありません）", ["閉じる"], "error"), label="バックアップ中")

    def bk_app(self):
        self.win.run(lambda: self.core.backups.create("app", "アプリデータ", self.core.app_data_files()),
                     lambda e: (self.win.toast.show("バックアップしました", "ok"), self.win.refresh_all()),
                     lambda e: choose(self.win, "バックアップできません", str(e), ["閉じる"], "error"), label="バックアップ中")

    def set_dir(self):
        d = QFileDialog.getExistingDirectory(self.win, "バックアップ保存先", str(self.core.backup_dir()))
        if d:
            self.core.settings.data.backup_dir = d
            if self._try(self.core.settings.save)[1]: self.win.refresh_all()

    def reset_dir(self):
        self.core.settings.data.backup_dir = ""; self._try(self.core.settings.save); self.win.refresh_all()

    def restore(self):
        bid = self._sel(); e = self.core.backups.get(bid) if bid else None
        if not e:
            self.win.toast.show("バックアップを選択してください", "warn"); return
        targets = "\n".join(m["source"] for m in e.files)
        if choose(self.win, "復元の確認", f"{fmt_dt(e.created_at)} のバックアップから復元します。\n次のファイルが上書きされます（上書き前に現在の内容を自動退避します）:\n\n{targets}", ["復元する", "キャンセル"], "warn") != 0:
            return
        self.win.run(lambda: self.core.backups.restore(bid), self._restored, self._restore_err, label="復元中")

    def _restored(self, done):
        self.core.reload_all(); self.win.refresh_all(); self.win.toast.show(f"{len(done)}件を復元しました", "ok")

    def _restore_err(self, e):
        hint = "" if isinstance(e, RestoreError) else "\n\n復旧手順: Robloxを終了し、権限・空き容量を確認して再試行してください。"
        choose(self.win, "復元に失敗しました", f"{e}{hint}", ["閉じる"], "error")

    def delete(self):
        bid = self._sel()
        if bid and choose(self.win, "削除の確認", "選択したバックアップを削除します。元に戻せません。", ["削除", "キャンセル"], "warn") == 0:
            self.core.backups.delete(bid); self.win.refresh_all()

    def prune_now(self):
        s = self.core.settings.data
        if choose(self.win, "整理の確認", f"最大{s.backup_max_count}件を超えるもの、または{s.backup_max_days or '無期限'}日を超えるものを削除します。", ["整理する", "キャンセル"], "warn") == 0:
            n = self.core.backups.prune(s.backup_max_count, s.backup_max_days)
            self.win.toast.show(f"{n}件を削除しました", "ok"); self.win.refresh_all()


# ───────────────────────── ログ・診断 ─────────────────────────
class LogPage(Page):
    title = "ログ・診断"

    def __init__(self, win):
        super().__init__(win)
        self.level = QComboBox(); self.level.addItems(["すべて", "WARNING以上", "ERRORのみ"]); self.level.currentIndexChanged.connect(self.refresh)
        self.root.addLayout(row(self.level, btn("更新", self.refresh), btn("Roblox環境を診断", self.diagnose), btn("診断ログをエクスポート", self.export),
                                btn("ログフォルダを開く", lambda: open_folder(self.core.paths.logs)), stretch=True))
        self.view = QPlainTextEdit(); self.view.setReadOnly(True); self.view.setMinimumHeight(420); self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.root.addWidget(self.view, 1)
        self.timer = QTimer(self); self.timer.setInterval(2500); self.timer.timeout.connect(self.refresh)

    def showEvent(self, e): self.timer.start(); super().showEvent(e)
    def hideEvent(self, e): self.timer.stop(); super().hideEvent(e)

    def refresh(self):
        lv = self.level.currentIndex()
        lines = [l for l in list(MEMORY.lines)[-600:] if lv == 0 or (lv == 1 and ("[WARNING]" in l or "[ERROR]" in l or "[CRITICAL]" in l)) or (lv == 2 and ("[ERROR]" in l or "[CRITICAL]" in l))]
        sb = self.view.verticalScrollBar(); at_end = sb.value() >= sb.maximum() - 4
        self.view.setPlainText("\n".join(lines))
        if at_end: sb.setValue(sb.maximum())

    def diagnose(self):
        self.win.redetect(lambda: TextDialog(self.win, "Roblox環境の診断", "検出結果", self.core.diagnostics_text().split("---- ログ ----")[0]).exec())

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self.win, "診断ログの保存先", f"polaris_diagnostics_{datetime.now():%Y%m%d_%H%M%S}.txt", "テキスト (*.txt)")
        if path:
            self.win.run(lambda: self.core.export_diagnostics(Path(path)), lambda p: self.win.toast.show("エクスポートしました（個人情報・認証情報はマスク済み）", "ok", 4500),
                         lambda e: choose(self.win, "保存できません", str(e), ["閉じる"], "error"), label="エクスポート中")


# ───────────────────────── 設定 ─────────────────────────
class SettingsPage(Page):
    title = "設定"

    def __init__(self, win):
        super().__init__(win)
        f, v = card("動作")
        self.anim = QCheckBox("アニメーションを有効にする"); self.confirm = QCheckBox("適用前に変更内容の確認を表示する")
        self.autoal = QCheckBox("起動時に公式許可リストを自動確認する（通信あり）")
        self.fmt = QComboBox(); self.fmt.addItem("文字列（\"True\" / \"5\"）— Bloxstrap互換", "string"); self.fmt.addItem("JSONの型のまま（true / 5）", "native")
        self.mode = QComboBox(); self.mode.addItem("設定を適用して起動", "apply_and_play"); self.mode.addItem("設定なしで通常起動", "play_only")
        for w in (self.anim, self.confirm, self.autoal):
            v.addWidget(w)
        v.addWidget(lbl("Robloxへ書き出す値の形式（実機での挙動は未検証）", "muted")); v.addWidget(self.fmt)
        v.addWidget(lbl("ライブラリでダブルクリックした時の起動方法", "muted")); v.addWidget(self.mode)
        self.root.addWidget(f)
        flook, vl = card("外観")
        self.accent = QComboBox()
        for name, color in (("Polaris Violet", "#7c5cff"), ("Ocean Blue", "#2997ff"), ("Aurora Cyan", "#00c7be"), ("Rose", "#f05b9b"), ("Amber", "#e6a23c"), ("カスタム色…", "custom")):
            self.accent.addItem(name, color)
        self.background_label = lbl("ホーム背景: 既定", "muted")
        vl.addWidget(lbl("アクセントカラー（選択後すぐ反映）", "muted")); vl.addWidget(self.accent)
        vl.addWidget(self.background_label)
        vl.addLayout(row(btn("背景動画・画像を選択", self.pick_background), btn("背景を解除", self.clear_background), stretch=True))
        self.root.addWidget(flook)
        f2, v2 = card("Roblox環境・データ")
        self.pin = lbl(name="muted"); v2.addWidget(self.pin)
        v2.addLayout(row(btn("Roblox環境を手動選択", self.pick_env), btn("手動選択を解除", self.unpin), btn("データフォルダを開く", lambda: open_folder(self.core.paths.root)), stretch=True))
        v2.addLayout(row(btn("設定を初期化", self.reset, "danger"), stretch=True))
        self.root.addWidget(f2); self.root.addStretch()
        self._loading = False
        for w, sig in ((self.anim, self.anim.toggled), (self.confirm, self.confirm.toggled), (self.autoal, self.autoal.toggled),
                       (self.fmt, self.fmt.currentIndexChanged), (self.mode, self.mode.currentIndexChanged)):
            sig.connect(self._save)
        self.accent.currentIndexChanged.connect(self._accent_changed)

    def refresh(self):
        s = self.core.settings.data; self._loading = True
        self.anim.setChecked(s.animations); self.confirm.setChecked(s.confirm_before_apply); self.autoal.setChecked(s.auto_check_allowlist)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(s.value_format))); self.mode.setCurrentIndex(max(0, self.mode.findData(s.default_launch_mode)))
        self.pin.setText("手動選択した環境: " + (s.pinned_version_dir or "なし（自動判定）") + "\n※公式情報・プロトコル登録で判定できる場合はそちらを優先します。")
        idx = self.accent.findData(s.accent_color)
        self.accent.setCurrentIndex(idx if idx >= 0 else self.accent.findData("custom"))
        self.background_label.setText("ホーム背景: " + (Path(s.home_background).name if s.home_background and Path(s.home_background).is_file() else "既定") + "（MP4などの動画は自動ループ・音声ミュート）")
        self._loading = False
        self.win.apply_home_background()

    def _accent_changed(self, *_):
        if self._loading: return
        color = self.accent.currentData()
        if color == "custom":
            from PySide6.QtGui import QColor
            chosen = QColorDialog.getColor(QColor(self.core.settings.data.accent_color), self.win, "アクセントカラーを選択")
            if not chosen.isValid():
                self.refresh(); return
            color = chosen.name()
        self.core.settings.data.accent_color = color
        self.core.settings.save()
        from .theme import apply_theme
        from PySide6.QtWidgets import QApplication
        apply_theme(QApplication.instance(), color)
        self.win.toast.show("アクセントカラーを変更しました", "ok", 1800)

    def pick_background(self):
        path, _ = QFileDialog.getOpenFileName(self.win, "ホーム背景メディアを選択", "", "動画・画像 (*.mp4 *.mov *.m4v *.avi *.mkv *.webm *.png *.jpg *.jpeg *.webp *.bmp);;動画 (*.mp4 *.mov *.m4v *.avi *.mkv *.webm);;画像 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.core.settings.data.home_background = path
            self.core.settings.save(); self.refresh()
            self.win.toast.show("ホーム背景を設定しました", "ok", 1800)

    def clear_background(self):
        self.core.settings.data.home_background = ""
        self.core.settings.save(); self.refresh()
        self.win.toast.show("ホーム背景を解除しました", "ok", 1800)

    def _save(self, *_):
        if self._loading: return
        s = self.core.settings.data
        s.animations, s.confirm_before_apply, s.auto_check_allowlist = self.anim.isChecked(), self.confirm.isChecked(), self.autoal.isChecked()
        s.value_format, s.default_launch_mode = self.fmt.currentData(), self.mode.currentData()
        ANIM["on"] = s.animations
        try:
            self.core.settings.save(); self.win.toast.show("設定を保存しました", "ok", 1800)
        except StorageError as e:
            choose(self.win, "保存できません", str(e), ["閉じる"], "error")

    def pick_env(self):
        c = [str(x) for x in self.core.detector.candidates()]
        if not c:
            self.win.toast.show("有効なRoblox環境が見つかりません", "warn"); return
        item, ok = QInputDialog.getItem(self.win, "Roblox環境の選択", "使用する環境:", c, 0, False)
        if ok:
            self.core.settings.data.pinned_version_dir = item; self.core.settings.save(); self.win.redetect()

    def unpin(self):
        self.core.settings.data.pinned_version_dir = ""; self.core.settings.save(); self.win.redetect()

    def reset(self):
        if choose(self.win, "設定の初期化", "アプリ設定を初期値に戻します（ゲーム・フラグ・プリセットは消えません）。", ["初期化", "キャンセル"], "warn") == 0:
            keep_pre = self.core.settings.data.active_preset
            self.core.settings.data = AppSettings(active_preset=keep_pre); self.core.settings.save()
            ANIM["on"] = True
            from .theme import apply_theme
            from PySide6.QtWidgets import QApplication
            apply_theme(QApplication.instance(), self.core.settings.data.accent_color)
            self.win.refresh_all(); self.win.toast.show("初期化しました", "ok")


# ───────────────────────── アプリ情報 ─────────────────────────
class AboutPage(Page):
    title = "アプリ情報"

    def __init__(self, win):
        super().__init__(win)
        f, v = card()
        pm = QLabel(); pm.setPixmap(QPixmap(str(assets.path("polaris_wordmark_white.png"))).scaledToHeight(64, Qt.SmoothTransformation))
        v.addWidget(pm); v.addWidget(lbl(f"{APP_NAME} v{__version__} ／ Windows向けRobloxカスタムランチャー（非公式）"))
        v.addWidget(lbl("Robloxの認証情報の取得・保存、コード注入、保護機能の回避は行いません。", "muted"))
        self.root.addWidget(f)
        f2, v2 = card("機能の状態（正直な一覧）")
        t = QPlainTextEdit(); t.setReadOnly(True); t.setMinimumHeight(330)
        t.setPlainText(FEATURES); v2.addWidget(t); self.root.addWidget(f2)


FEATURES = """【実装済み・自動テスト済み（Robloxをモックした単体テスト）】
 Place ID/URL解析・検証 / JSON安全読み書き・破損復旧 / FastFlag追加・編集・削除・検証・重複検出
 プリセット管理 / バックアップ作成・復元・自動整理 / Roblox環境検出（未インストール・複数環境・更新後の再検出）
 ClientAppSettings.jsonへの適用（一時ファイル→検証→置換、失敗時ロールバック）/ 起動フロー / ログのマスキング

【実装済み・Windows実機のRobloxでは未検証（要確認）】
 roblox://experiences/start?placeId=… による起動要求（os.startfile）
 「Robloxを通常起動」（RobloxPlayerLauncher.exe の直接起動）
 値を文字列化して書き出す形式がRoblox側で受理されること
 公式許可リストの自動取得（DevForum公式投稿の1つ目の投稿から抽出。形式が変わると失敗します）

【できないこと（仕様上の制限）】
 ・ゲームへ「実際に接続できたか」の確認 … 起動要求の送信とプロセス検出までしか判定できません
 ・公式許可リストに無いフラグの反映 … Robloxに無視されます
 ・プライベートサーバー等の参加権限の迂回 … 行いません（通常のRobloxの認証フローに従います）"""
