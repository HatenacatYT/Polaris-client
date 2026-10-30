"""共通ダイアログ（表示・終了のフェード付き）。"""
from __future__ import annotations
from ..core.i18n import tr, N_
import json
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QMessageBox, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLabel, QLineEdit, QComboBox, QFormLayout,
                               QDialogButtonBox)

from ..core.flags import CATEGORIES, check_preset_name, loads_checked
from ..core.games import parse_place_input, InvalidPlace
from .widgets import AnimButton, FadeDialog, FadeMessageBox

ICONS = {"question": QMessageBox.Question, "info": QMessageBox.Information, "warn": QMessageBox.Warning, "error": QMessageBox.Critical}
SYMBOL = {"ok": "✔", "warn": "⚠", "fail": "✖", "skip": "－"}


def choose(parent, title, text, labels, icon="question", detail="") -> int:
    """ボタンを自由に並べて選択させる。最後のボタンがEsc/閉じる扱い。戻り値=インデックス。"""
    box = FadeMessageBox(parent)
    box.setWindowTitle(title); box.setText(text); box.setIcon(ICONS[icon])
    if detail:
        box.setDetailedText(detail)
    btns = [box.addButton(l, QMessageBox.ActionRole) for l in labels]
    box.setEscapeButton(btns[-1]); box.setDefaultButton(btns[0])
    box.exec()
    clicked = box.clickedButton()
    return btns.index(clicked) if clicked in btns else len(btns) - 1


def steps_text(steps) -> str:
    return "\n".join(f"{SYMBOL.get(s.status, '?')} {s.name}" + (f" — {s.detail}" if s.detail else "") for s in steps)


def open_folder(path):
    Path(path).mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_url(url: str) -> bool:
    return QDesktopServices.openUrl(QUrl(url))   # OSの既定ブラウザ


def _buttons(dlg, ok_text, cancel_text, on_ok):
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(ok_text); bb.button(QDialogButtonBox.Cancel).setText(cancel_text)
    bb.accepted.connect(on_ok); bb.rejected.connect(dlg.reject)
    return bb


class TextDialog(FadeDialog):
    def __init__(self, parent, title, header, body, ok="OK", cancel=None):
        super().__init__(parent)
        self.setWindowTitle(title); self.resize(680, 460)
        lay = QVBoxLayout(self)
        h = QLabel(header); h.setWordWrap(True); lay.addWidget(h)
        t = QPlainTextEdit(body); t.setReadOnly(True); lay.addWidget(t, 1)
        row = QHBoxLayout(); row.addStretch()
        if cancel:
            b = AnimButton(cancel); b.clicked.connect(self.reject); row.addWidget(b)
        b = AnimButton(ok, "primary"); b.clicked.connect(self.accept); row.addWidget(b)
        lay.addLayout(row)


class NameDialog(FadeDialog):
    """名前入力。validator(text)->エラー文字列（空なら有効）。無効な間はOKできない。"""
    def __init__(self, parent, title, label, text="", validator=None, ok="OK"):
        super().__init__(parent)
        self.setWindowTitle(title); self.setMinimumWidth(460); self.validator = validator
        f = QFormLayout(self)
        self.edit = QLineEdit(text); self.edit.selectAll()
        self.err = QLabel(""); self.err.setStyleSheet("color:#ff5c5c;"); self.err.setWordWrap(True)
        f.addRow(label, self.edit); f.addRow(self.err); f.addRow(_buttons(self, ok, tr("キャンセル"), self._ok))

    def _ok(self):
        e = self.validator(self.edit.text()) if self.validator else ""
        if e:
            self.err.setText(e); return
        self.accept()

    def value(self) -> str:
        return self.edit.text().strip()


class PresetActionDialog(FadeDialog):
    """プリセット項目をクリックした時の操作メニュー。"""
    def __init__(self, parent, name, in_use):
        super().__init__(parent)
        self.setWindowTitle(name); self.setMinimumWidth(380); self.action = None
        v = QVBoxLayout(self); v.setSpacing(8)
        t = QLabel(name); t.setObjectName("h2"); t.setWordWrap(True); v.addWidget(t)
        if in_use:
            u = QLabel(tr("現在使用中のプリセットです")); u.setObjectName("muted"); v.addWidget(u)
        for key, text, var in (("use", tr("このプリセットを使用する"), "primary"), ("edit", tr("編集する"), "secondary"),
                               ("rename", tr("名前を変更する"), "secondary"), ("dup", tr("複製する"), "secondary"),
                               ("export", tr("エクスポートする"), "secondary"), ("delete", tr("削除する"), "danger")):
            b = AnimButton(text, var); b.clicked.connect(lambda _=False, k=key: self._pick(k)); v.addWidget(b)
        c = AnimButton(tr("キャンセル"), "ghost"); c.clicked.connect(self.reject); v.addWidget(c)

    def _pick(self, k):
        self.action = k; self.accept()


class NewPresetDialog(FadeDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("FastFlagsの新規作成")); self.setMinimumWidth(560)
        f = QFormLayout(self)
        self.name, self.desc = QLineEdit(), QLineEdit()
        self.cat = QComboBox()
        for c in CATEGORIES:
            self.cat.addItem(c, c)
        self.cat.setCurrentIndex(self.cat.findData("その他"))
        self.js = QPlainTextEdit(); self.js.setPlaceholderText(tr('空のままなら空のプリセットを作成します。\n{ "FFlagExample": true, "FIntExample": 5 }')); self.js.setMinimumHeight(140)
        self.err = QLabel(""); self.err.setStyleSheet("color:#ff5c5c;"); self.err.setWordWrap(True)
        for l, w in ((tr("プリセット名"), self.name), (tr("説明（任意）"), self.desc), (tr("カテゴリ"), self.cat), (tr("初期状態のFastFlags（JSON・任意）"), self.js)):
            f.addRow(l, w)
        f.addRow(self.err); f.addRow(_buttons(self, tr("作成"), tr("キャンセル"), self._ok))

    def _ok(self):
        bad = check_preset_name(self.name.text())
        if bad:
            self.err.setText(bad); return
        txt = self.js.toPlainText().strip()
        self.flags = {}
        if txt:
            data, dups, errs = loads_checked(txt)
            if data is None or errs:
                self.err.setText("\n".join(errs[:6])); return
            self.flags = data
        self.accept()

    def values(self):
        return self.name.text().strip(), self.cat.currentData(), self.desc.text().strip(), self.flags


class AddGameDialog(FadeDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(tr("ゲームを追加")); self.setMinimumWidth(520)
        f = QFormLayout(self)
        self.inp = QLineEdit(); self.inp.setPlaceholderText(tr("Place ID、または https://www.roblox.com/games/<ID>/..."))
        self.name = QLineEdit(); self.name.setPlaceholderText(tr("空欄なら『Place <ID>』（後で変更可）"))
        self.err = QLabel(""); self.err.setStyleSheet("color:#ff5c5c;"); self.err.setWordWrap(True)
        fetch = AnimButton(tr("ゲーム名を取得（通信）")); fetch.clicked.connect(self._fetch)
        f.addRow("Place ID / URL", self.inp); f.addRow(tr("ゲーム名"), self.name); f.addRow("", fetch); f.addRow(self.err)
        f.addRow(_buttons(self, tr("追加"), tr("キャンセル"), self._ok))

    def _parse(self):
        try:
            return parse_place_input(self.inp.text())
        except InvalidPlace as e:
            self.err.setText(str(e)); return None

    def _fetch(self):
        pid = self._parse()
        if pid is None:
            return
        from ..core.games import fetch_game_name
        self.err.setText(tr("取得中…"))
        self.win.run(lambda: fetch_game_name(pid), self._got, self._fail, label=tr("ゲーム名を取得中"))

    def _got(self, n): self.name.setText(n); self.err.setText("")
    def _fail(self, e): self.err.setText(tr("名前を取得できませんでした（手入力もできます）: {0}", e))

    def _ok(self):
        if self._parse() is not None:
            self.accept()

    def values(self): return self.inp.text(), self.name.text()
