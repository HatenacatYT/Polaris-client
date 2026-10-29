"""共通ダイアログ。"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLabel, QLineEdit, QComboBox,
                               QFormLayout, QDialogButtonBox, QCheckBox)

from ..core.flags import CATEGORIES, parse_value_text, validate_flag
from ..core.games import parse_place_input, InvalidPlace
from .widgets import AnimButton

ICONS = {"question": QMessageBox.Question, "info": QMessageBox.Information, "warn": QMessageBox.Warning, "error": QMessageBox.Critical}
SYMBOL = {"ok": "✔", "warn": "⚠", "fail": "✖", "skip": "－"}


def choose(parent, title, text, labels, icon="question", detail="") -> int:
    """ボタンを自由に並べて選択させる。最後のボタンがEsc/閉じる扱い。戻り値=インデックス。"""
    box = QMessageBox(parent)
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


class TextDialog(QDialog):
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


class AddGameDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("ゲームを追加"); self.setMinimumWidth(520)
        f = QFormLayout(self)
        self.inp = QLineEdit(); self.inp.setPlaceholderText("Place ID、または https://www.roblox.com/games/<ID>/...")
        self.name = QLineEdit(); self.name.setPlaceholderText("空欄なら『Place <ID>』（後で変更可）")
        self.err = QLabel(""); self.err.setStyleSheet("color:#ff5c5c;"); self.err.setWordWrap(True)
        fetch = AnimButton("ゲーム名を取得（通信）"); fetch.clicked.connect(self._fetch)
        f.addRow("Place ID / URL", self.inp); f.addRow("ゲーム名", self.name); f.addRow("", fetch); f.addRow(self.err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("追加"); bb.button(QDialogButtonBox.Cancel).setText("キャンセル")
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); f.addRow(bb)

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
        self.err.setText("取得中…")
        self.win.run(lambda: fetch_game_name(pid), self._got, self._fail, label="ゲーム名を取得中")

    def _got(self, n): self.name.setText(n); self.err.setText("")
    def _fail(self, e): self.err.setText(f"名前を取得できませんでした（手入力もできます）: {e}")

    def _ok(self):
        if self._parse() is not None:
            self.accept()

    def values(self): return self.inp.text(), self.name.text()


class AddFlagDialog(QDialog):
    def __init__(self, parent, allow_status):
        super().__init__(parent)
        self.allow_status = allow_status
        self.setWindowTitle("フラグを追加"); self.setMinimumWidth(480)
        f = QFormLayout(self)
        self.name = QLineEdit(); self.value = QLineEdit(); self.value.setPlaceholderText('true / 12 / "文字列" / True（JSONとして解釈できなければ文字列）')
        self.cat = QComboBox(); self.cat.addItems(CATEGORIES); self.cat.setCurrentText("その他")
        self.note = QLineEdit()
        self.err = QLabel(""); self.err.setStyleSheet("color:#ff5c5c;"); self.err.setWordWrap(True)
        for l, w in (("フラグ名", self.name), ("値", self.value), ("カテゴリ", self.cat), ("メモ", self.note)):
            f.addRow(l, w)
        f.addRow(self.err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("追加"); bb.button(QDialogButtonBox.Cancel).setText("キャンセル")
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject); f.addRow(bb)

    def _ok(self):
        try:
            v = parse_value_text(self.value.text())
            errs = validate_flag(self.name.text().strip(), v)
            if errs:
                raise ValueError("; ".join(errs))
        except ValueError as e:
            self.err.setText(str(e)); return
        self.parsed = v
        self.accept()

    def values(self): return self.name.text().strip(), self.parsed, self.cat.currentText(), self.note.text()


class BulkDialog(QDialog):
    ACTIONS = ["有効にする", "無効にする", "お気に入りに追加", "お気に入りから外す", "カテゴリを変更", "選択を削除"]

    def __init__(self, parent, n):
        super().__init__(parent)
        self.setWindowTitle(f"一括編集（{n}件）")
        f = QFormLayout(self)
        self.act = QComboBox(); self.act.addItems(self.ACTIONS)
        self.cat = QComboBox(); self.cat.addItems(CATEGORIES)
        f.addRow("操作", self.act); f.addRow("カテゴリ", self.cat)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("実行"); bb.button(QDialogButtonBox.Cancel).setText("キャンセル")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); f.addRow(bb)
