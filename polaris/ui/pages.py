"""各ページ。すべて refresh() で最新状態を描画する。"""
from __future__ import annotations
from ..core.i18n import tr, N_
import json
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QLineEdit, QComboBox, QTableWidget,
                               QTableWidgetItem, QAbstractItemView, QHeaderView, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QCheckBox, QSpinBox, QFileDialog, QInputDialog, QSplitter, QScrollArea)

from .. import __version__, APP_NAME
from ..core.flags import (CATEGORIES, EDITOR_PRESET_ID, parse_value_text, loads_checked, validate_flags, to_roblox_payload,
                          value_type, validate_flag)
from ..core.jsonio import StorageError, write_json
from ..core.allowlist import AllowlistError
from ..core.backup import RestoreError
from ..core.logsetup import MEMORY
from ..core.roblox import client_settings_path
from .dialogs import choose, TextDialog, AddGameDialog, open_folder, steps_text
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


def backup_label(label: str) -> str:
    """バックアップのラベルは言語に依存しない識別子で保存され、表示時に翻訳する。"""
    if label == "pre-apply": return tr("FastFlag適用前")
    if label == "manual": return tr("手動バックアップ")
    if label == "app-data": return tr("アプリデータ")
    if label.startswith("pre-restore:"): return tr("復元前の自動退避 ({0})", label.split(':', 1)[1])
    return label


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
        self.root.addWidget(lbl(tr(self.title), "h1"))

    def refresh(self): pass


# ───────────────────────── ホーム ─────────────────────────
class StatusPage(Page):
    title = N_("Roblox環境")

    def __init__(self, win):
        super().__init__(win)
        g = QGridLayout(); g.setSpacing(14); self.root.addLayout(g)
        c1, v1 = card(tr("Roblox環境"))
        self.l_status, self.l_ver, self.l_path, self.l_by, self.l_time = (lbl() for _ in range(5))
        for w in (self.l_status, self.l_ver, self.l_path, self.l_by, self.l_time):
            v1.addWidget(w)
        v1.addLayout(row(btn(tr("再検出"), win.redetect), btn(tr("診断情報を表示"), self.show_diag), stretch=True))
        c2, v2 = card("FastFlag")
        self.l_apply, self.l_allow = lbl(), lbl(name="muted")
        v2.addWidget(self.l_apply); v2.addWidget(self.l_allow)
        self.cmb = QComboBox(); self.cmb.currentIndexChanged.connect(self._preset_changed)
        v2.addWidget(lbl(tr("プリセットのクイック選択"), "muted")); v2.addWidget(self.cmb)
        v2.addLayout(row(btn(tr("設定を適用"), self.apply_only, "primary"), btn(tr("Robloxを通常起動"), self.roblox_only), stretch=True))
        c3, v3 = card(tr("ゲーム"))
        self.l_last = lbl()
        v3.addWidget(self.l_last)
        self.l_recent, self.l_fav = QListWidget(), QListWidget()
        for l in (self.l_recent, self.l_fav):
            l.setMaximumHeight(150); l.itemDoubleClicked.connect(lambda it: self.play(True, it))
        v3.addWidget(lbl(tr("最近のゲーム（ダブルクリックで起動）"), "muted")); v3.addWidget(self.l_recent)
        v3.addWidget(lbl(tr("お気に入り"), "muted")); v3.addWidget(self.l_fav)
        v3.addLayout(row(btn(tr("▶ 選択ゲームを起動（設定を適用）"), lambda: self.play(True), "primary"),
                         btn(tr("設定なしで起動"), lambda: self.play(False)), stretch=True))
        g.addWidget(c1, 0, 0); g.addWidget(c2, 0, 1); g.addWidget(c3, 1, 0, 1, 2)
        g.setColumnStretch(0, 1); g.setColumnStretch(1, 1)
        c4, v4 = card(tr("直近の結果"))
        self.out = QPlainTextEdit(); self.out.setReadOnly(True); self.out.setMinimumHeight(110)
        self.out.setPlainText(tr("まだ操作は行われていません。"))
        v4.addWidget(self.out); self.root.addWidget(c4); self.root.addStretch()

    def selected_game(self):
        for lw in (self.l_recent, self.l_fav):
            it = lw.currentItem()
            if it is not None and lw.hasFocus():
                return self.core.games.get(it.data(UR))
        for lw in (self.l_recent, self.l_fav):
            it = lw.currentItem()
            if it is not None:
                return self.core.games.get(it.data(UR))
        return None

    def play(self, apply: bool, item=None):
        g = self.core.games.get(item.data(UR)) if item is not None else self.selected_game()
        if g is None:
            self.win.toast.show(tr("ゲームを選択してください（ゲームライブラリで追加できます）"), "warn"); return
        self.win.launch.start(g, "apply_and_play" if apply else "play_only")

    def apply_only(self):
        self.win.launch.start(None, "apply_only", self.core.settings.data.active_preset)

    def roblox_only(self):
        self.win.launch.start(None, "roblox_only")

    def show_diag(self):
        TextDialog(self.win, tr("診断情報"), tr("個人情報・認証情報はマスクされています。"), self.core.diagnostics_text()).exec()

    def _preset_changed(self):
        if getattr(self, "_loading", False):
            return
        self.core.settings.data.active_preset = self.cmb.currentData() or ""
        self.core.settings.save()

    def refresh(self):
        c, d = self.core, self.core.last_detection
        if d.install:
            i = d.install
            self.l_status.setText(tr("<b style='color:{0}'>● 検出済み</b>", OK))
            self.l_ver.setText(tr("バージョン: {0}", i.version_name)); self.l_path.setText(tr("インストール先: {0}", i.version_dir))
            self.l_by.setText(tr("判定根拠: {0}（有効な環境 {1}件）", i.verified_by, i.candidate_count)); self.l_time.setText(tr("検出日時: {0}", fmt_dt(i.detected_at)))
        else:
            self.l_status.setText(tr("<b style='color:{0}'>● {1}</b>　{2}", ERR if d.code != 'NOT_CHECKED' else WARN, tr('未検出') if d.code in ('NOT_FOUND','NOT_CHECKED') else tr('確認できません'), d.message))
            for l in (self.l_ver, self.l_path, self.l_by, self.l_time):
                l.setText(tr("確認できません"))
        la = c.state.get("last_apply")
        if la:
            st = tr("成功") if la.get("ok") else tr("失敗")
            extra = tr("（未確認フラグ {0}件）", la['unverified']) if la.get("unverified") else ""
            self.l_apply.setText(tr("最終適用: {0} ／ {1} ／ {2}件{3}\n※書き込み成功であり、Roblox内で反映された保証ではありません。", fmt_dt(la.get('at')), st, la.get('count', 0), extra)
                                 + (tr("\n<b style='color:%s'>⚠ Robloxのバージョンが変わっています。再適用してください。</b>") % WARN if c.needs_reapply() else ""))
        else:
            self.l_apply.setText(tr("FastFlagの適用履歴: なし"))
        self.l_allow.setText(tr("公式許可リスト: ") + c.allowlist.state_text())
        self._loading = True
        self.cmb.clear()
        for pid, name in c.preset_choices():
            self.cmb.addItem(name, pid)
        self.cmb.setCurrentIndex(max(0, self.cmb.findData(c.settings.data.active_preset)))
        self._loading = False
        lg = c.state.get("last_game")
        self.l_last.setText(tr("最後に起動: {0}（{1}）", lg['name'], fmt_dt(lg['at'])) if lg else tr("最後に起動したゲーム: なし"))
        for lw, games in ((self.l_recent, c.games.recent(8)), (self.l_fav, c.games.favorites())):
            lw.clear()
            for g in games:
                it = QListWidgetItem(tr("{0}{1}　(起動{2}回)", '★ ' if g.favorite else '', g.name, g.launch_count)); it.setData(UR, g.id); lw.addItem(it)


# ───────────────────────── ゲームライブラリ ─────────────────────────
class GamesPage(Page):
    title = N_("ゲームライブラリ")

    def __init__(self, win):
        super().__init__(win)
        self.cur = None
        top = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText(tr("ゲーム名・Place IDで検索")); self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search, 1); top.addWidget(btn(tr("＋ ゲームを追加"), self.add, "primary")); self.root.addLayout(top)
        sp = QSplitter(); self.root.addWidget(sp, 1)
        self.table = make_table(["★", tr("ゲーム名"), "Place ID", tr("起動回数"), tr("最終起動")], [44, 240, 120, 80, 150])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self._select); self.table.cellDoubleClicked.connect(lambda *_: self.play(self.core.settings.data.default_launch_mode == "apply_and_play"))
        self.table.setMinimumHeight(320)
        sp.addWidget(self.table)
        f, v = card(tr("詳細"))
        self.name, self.pid = QLineEdit(), QLineEdit()
        self.note = QPlainTextEdit(); self.note.setPlaceholderText(tr("メモ")); self.note.setMaximumHeight(90)
        self.preset = QComboBox()
        self.fav = QCheckBox(tr("お気に入り")); self.apply_cb = QCheckBox(tr("起動時にFastFlagを適用する")); self.verify_cb = QCheckBox(tr("起動後にRobloxプロセスを確認する"))
        for t, w in ((tr("ゲーム名"), self.name), ("Place ID", self.pid), (tr("メモ"), self.note), (tr("FastFlagプリセット"), self.preset)):
            v.addWidget(lbl(t, "muted")); v.addWidget(w)
        for w in (self.fav, self.apply_cb, self.verify_cb):
            v.addWidget(w)
        v.addLayout(row(btn(tr("保存"), self.save, "primary"), btn(tr("削除"), self.delete, "danger"), stretch=True))
        v.addLayout(row(btn(tr("▶ プレイ（設定を適用）"), lambda: self.play(True), "primary"), btn(tr("設定なしで起動"), lambda: self.play(False)), stretch=True))
        v.addLayout(row(btn(tr("ホームの選択ゲームにする"), self.select_home), stretch=True))
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
        self.preset.addItem(tr("（ホームで選択中のプリセットを使う）"), "")
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
                self.cur = g.id; self.win.toast.show(tr("『{0}』を追加しました", g.name), "ok"); self.win.refresh_all()
            except (ValueError, StorageError) as e:
                choose(self.win, tr("追加できません"), str(e), [tr("閉じる")], "error")

    def save(self):
        if not self.cur:
            return
        try:
            from ..core.games import parse_place_input
            self.core.games.update(self.cur, name=self.name.text(), place_id=parse_place_input(self.pid.text()),
                                   note=self.note.toPlainText(), favorite=self.fav.isChecked(), apply_flags=self.apply_cb.isChecked(),
                                   verify_process=self.verify_cb.isChecked(), preset_id=self.preset.currentData() or "")
            self.win.toast.show(tr("保存しました"), "ok"); self.win.refresh_all()
        except (ValueError, StorageError) as e:
            choose(self.win, tr("保存できません"), str(e), [tr("閉じる")], "error")

    def delete(self):
        g = self.core.games.get(self.cur) if self.cur else None
        if g and choose(self.win, tr("ゲームの削除"), tr("『{0}』をライブラリから削除しますか？（Robloxのデータには影響しません）", g.name), [tr("削除"), tr("キャンセル")], "warn") == 0:
            self.core.games.delete(g.id); self.cur = None; self.win.refresh_all(); self.win.toast.show(tr("削除しました"), "ok")

    def select_home(self):
        g = self.core.games.get(self.cur) if self.cur else None
        if g is None:
            self.win.toast.show(tr("ゲームを選択してください"), "warn"); return
        self.core.select_game(g.id); self.win.refresh_all(); self.win.toast.show(tr("ホームの選択ゲームを『{0}』にしました", g.name), "ok")

    def play(self, apply: bool):
        g = self.core.games.get(self.cur) if self.cur else None
        if g is None:
            self.win.toast.show(tr("ゲームを選択してください"), "warn"); return
        self.save()
        self.win.launch.start(g, "apply_and_play" if apply else "play_only")


# ───────────────────────── バックアップ・復元 ─────────────────────────
class BackupsPage(Page):
    title = N_("バックアップ・復元")

    def __init__(self, win):
        super().__init__(win)
        self.dir_lbl = lbl(name="muted"); self.root.addWidget(self.dir_lbl)
        self.root.addLayout(row(btn(tr("Roblox設定をバックアップ"), self.bk_roblox), btn(tr("アプリデータをバックアップ"), self.bk_app),
                                btn(tr("保存先を変更"), self.set_dir), btn(tr("保存先を既定に戻す"), self.reset_dir), btn(tr("フォルダを開く"), lambda: open_folder(self.core.backup_dir())), stretch=True))
        self.table = make_table([tr("日時"), tr("種別"), tr("内容"), tr("対象パス")], [170, 100, 220, 400])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setSelectionMode(QAbstractItemView.SingleSelection); self.table.setMinimumHeight(280)
        self.root.addWidget(self.table, 1)
        self.root.addLayout(row(btn(tr("選択したバックアップから復元"), self.restore, "primary"), btn(tr("選択を削除"), self.delete, "danger"), stretch=True))
        f, v = card(tr("自動削除（既定ではオフ。ユーザーの同意なしに削除しません）"))
        self.auto = QCheckBox(tr("バックアップ作成後、古いものを自動削除する"))
        self.mx, self.days = QSpinBox(), QSpinBox()
        self.mx.setRange(1, 10000); self.days.setRange(0, 36500); self.days.setSpecialValueText(tr("無期限"))
        v.addWidget(self.auto)
        v.addLayout(row(lbl(tr("最大保存数")), self.mx, lbl(tr("保存期間(日)")), self.days, btn(tr("今すぐ整理"), self.prune_now), stretch=True))
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
        self.dir_lbl.setText(tr("保存先: {0}", self.core.backup_dir()))
        self.table.setRowCount(0)
        for e in self._entries():
            r = self.table.rowCount(); self.table.insertRow(r)
            for c, t in enumerate([fmt_dt(e.created_at), e.kind, backup_label(e.label), " / ".join(m["source"] for m in e.files)]):
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
            choose(self.win, tr("失敗しました"), str(e), [tr("閉じる")], "error"); return None, False

    def bk_roblox(self):
        def job():
            d = self.core.detect_outcome()
            if d.install is None: raise StorageError(d.message)
            return self.core.backups.create("roblox", "manual", [client_settings_path(d.install)])
        self.win.run(job, lambda e: (self.win.toast.show(tr("バックアップしました"), "ok"), self.win.refresh_all()),
                     lambda e: choose(self.win, tr("バックアップできません"), tr("{0}\n（ClientAppSettings.json が存在しない場合は対象がありません）", e), [tr("閉じる")], "error"), label=tr("バックアップ中"))

    def bk_app(self):
        self.win.run(lambda: self.core.backups.create("app", "app-data", self.core.app_data_files()),
                     lambda e: (self.win.toast.show(tr("バックアップしました"), "ok"), self.win.refresh_all()),
                     lambda e: choose(self.win, tr("バックアップできません"), str(e), [tr("閉じる")], "error"), label=tr("バックアップ中"))

    def set_dir(self):
        d = QFileDialog.getExistingDirectory(self.win, tr("バックアップ保存先"), str(self.core.backup_dir()))
        if d:
            self.core.settings.data.backup_dir = d
            if self._try(self.core.settings.save)[1]: self.win.refresh_all()

    def reset_dir(self):
        self.core.settings.data.backup_dir = ""; self._try(self.core.settings.save); self.win.refresh_all()

    def restore(self):
        bid = self._sel(); e = self.core.backups.get(bid) if bid else None
        if not e:
            self.win.toast.show(tr("バックアップを選択してください"), "warn"); return
        targets = "\n".join(m["source"] for m in e.files)
        if choose(self.win, tr("復元の確認"), tr("{0} のバックアップから復元します。\n次のファイルが上書きされます（上書き前に現在の内容を自動退避します）:\n\n{1}", fmt_dt(e.created_at), targets), [tr("復元する"), tr("キャンセル")], "warn") != 0:
            return
        self.win.run(lambda: self.core.backups.restore(bid), self._restored, self._restore_err, label=tr("復元中"))

    def _restored(self, done):
        self.core.reload_all(); self.win.refresh_all(); self.win.toast.show(tr("{0}件を復元しました", len(done)), "ok")

    def _restore_err(self, e):
        hint = "" if isinstance(e, RestoreError) else tr("\n\n復旧手順: Robloxを終了し、権限・空き容量を確認して再試行してください。")
        choose(self.win, tr("復元に失敗しました"), f"{e}{hint}", [tr("閉じる")], "error")

    def delete(self):
        bid = self._sel()
        if bid and choose(self.win, tr("削除の確認"), tr("選択したバックアップを削除します。元に戻せません。"), [tr("削除"), tr("キャンセル")], "warn") == 0:
            self.core.backups.delete(bid); self.win.refresh_all()

    def prune_now(self):
        s = self.core.settings.data
        if choose(self.win, tr("整理の確認"), tr("最大{0}件を超えるもの、または{1}日を超えるものを削除します。", s.backup_max_count, s.backup_max_days or tr('無期限')), [tr("整理する"), tr("キャンセル")], "warn") == 0:
            n = self.core.backups.prune(s.backup_max_count, s.backup_max_days)
            self.win.toast.show(tr("{0}件を削除しました", n), "ok"); self.win.refresh_all()


# ───────────────────────── ログ・診断 ─────────────────────────
class LogPage(Page):
    title = N_("ログ・診断")

    def __init__(self, win):
        super().__init__(win)
        self.level = QComboBox(); self.level.addItems([tr("すべて"), tr("WARNING以上"), tr("ERRORのみ")]); self.level.currentIndexChanged.connect(self.refresh)
        self.root.addLayout(row(self.level, btn(tr("更新"), self.refresh), btn(tr("Roblox環境を診断"), self.diagnose), btn(tr("診断ログをエクスポート"), self.export),
                                btn(tr("ログフォルダを開く"), lambda: open_folder(self.core.paths.logs)), stretch=True))
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
        self.win.redetect(lambda: TextDialog(self.win, tr("Roblox環境の診断"), tr("検出結果"), self.core.diagnostics_text().split(tr("---- ログ ----"))[0]).exec())

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self.win, tr("診断ログの保存先"), f"polaris_diagnostics_{datetime.now():%Y%m%d_%H%M%S}.txt", tr("テキスト (*.txt)"))
        if path:
            self.win.run(lambda: self.core.export_diagnostics(Path(path)), lambda p: self.win.toast.show(tr("エクスポートしました（個人情報・認証情報はマスク済み）"), "ok", 4500),
                         lambda e: choose(self.win, tr("保存できません"), str(e), [tr("閉じる")], "error"), label=tr("エクスポート中"))


