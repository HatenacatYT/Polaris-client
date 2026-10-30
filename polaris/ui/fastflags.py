"""FastFlags: 保存済みプリセット一覧と、独立した編集画面。
プリセット管理（保存）とRobloxへの適用（launcher/applier）は分離されている。"""
from __future__ import annotations
from ..core.i18n import tr, N_
import copy
import json
import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QFileDialog, QAbstractItemView, QTableWidgetItem)

from ..core.allowlist import AllowlistError
from ..core.flags import (loads_checked, validate_flags, validate_flag, parse_value_text, to_roblox_payload, value_type,
                          check_preset_name)
from ..core.jsonio import StorageError, write_json
from .dialogs import choose, TextDialog, NameDialog, PresetActionDialog, NewPresetDialog
from .pages import Page, lbl, card, row, btn, fmt_dt, make_table
from .theme import MUTED, OK, WARN, ERR
from .widgets import AnimButton

UR = Qt.UserRole
ALLOW_TEXT = {"allowed": N_("公式掲載"), "not_listed": N_("未掲載（無視される可能性）"), "unverified": N_("未確認（リスト未取得/期限切れ）")}


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip() or "preset"


class PresetCard(QFrame):
    clicked = Signal(str)

    def __init__(self, p: dict, in_use: bool, state_text: str, flag_word: str):
        super().__init__()
        self.pid = p["id"]; self.setObjectName("presetCard"); self.setCursor(Qt.PointingHandCursor); self.setFocusPolicy(Qt.StrongFocus)
        v = QVBoxLayout(self); v.setContentsMargins(18, 14, 18, 14); v.setSpacing(4)
        top = QHBoxLayout(); top.setSpacing(8)
        n = QLabel(p["name"]); n.setObjectName("h2"); top.addWidget(n)
        if in_use:
            b = QLabel(tr("使用中")); b.setObjectName("badge"); top.addWidget(b)
        top.addStretch(); c = QLabel(p.get("category", "")); c.setObjectName("muted"); top.addWidget(c)
        v.addLayout(top)
        if p.get("description"):
            d = QLabel(p["description"]); d.setObjectName("muted"); d.setWordWrap(True); v.addWidget(d)
        m = QLabel(tr("{0} {1}  ・  最終更新 {2}  ・  {3}", len(p['flags']), flag_word, fmt_dt(p.get('updated_at', '')), state_text))
        m.setObjectName("muted"); m.setWordWrap(True); v.addWidget(m)
        for w in self.findChildren(QLabel):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAccessibleName(p["name"])

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.pid)
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self.pid)
        else:
            super().keyPressEvent(e)


class FlagsListPage(Page):
    title = "FastFlags"

    def __init__(self, win):
        super().__init__(win)
        self.root.addWidget(lbl(tr("保存済みのFastFlagsプリセットを管理します。プリセットを選ぶと『使用する・編集・名前変更・削除』ができます。"), "muted"))
        self.root.addLayout(row(btn(tr("＋ 新規作成"), self.new, "primary"), btn(tr("インポート"), self.import_),
                                btn(tr("▶ 使用中のプリセットをRobloxへ適用"), self.apply_now), stretch=True))
        self.note = lbl("", "muted"); self.root.addWidget(self.note)
        self.root.addLayout(row(btn(tr("公式許可リストを更新"), self.update_allow), btn(tr("許可リストをファイルから読込"), self.load_allow), stretch=True))
        self.box = QVBoxLayout(); self.box.setSpacing(10); self.root.addLayout(self.box); self.root.addStretch()

    def refresh(self):
        while self.box.count():
            it = self.box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        c = self.core
        self.note.setText(tr("公式許可リスト: ") + c.allowlist.state_text() +
                          tr("\n『設定ファイルへの保存完了』は、Robloxがそのフラグをゲーム内で有効にしたことを意味しません。公式リストに無いフラグはRobloxに無視されます。"))
        if not c.presets.presets:
            f, v = card(tr("まだプリセットがありません"))
            v.addWidget(lbl(tr("『新規作成』から最初のFastFlagsプリセットを作成しましょう。空のプリセットも作れ、JSONを貼り付けて始めることもできます。"), "muted"))
            v.addLayout(row(btn(tr("最初のプリセットを作成"), self.new, "primary"), stretch=True))
            self.box.addWidget(f); return
        for p in c.presets.presets:
            st, at = c.preset_apply_state(p["id"])
            text = {"applied": tr("Robloxの設定ファイルへ書き込み済み（{0}）"), "modified": tr("編集済み・未再適用"), "outdated": tr("Roblox更新後の再適用が必要"),
                    "none": tr("未適用")}[st]
            card_ = PresetCard(p, p["id"] == c.settings.data.active_preset, text.format(fmt_dt(at)) if st == "applied" else text, tr("フラグ"))
            card_.clicked.connect(self._clicked); self.box.addWidget(card_)

    # ---- 操作メニュー ----
    def _clicked(self, pid):
        p = self.core.presets.get(pid)
        if p is None:
            return
        dlg = PresetActionDialog(self.win, p["name"], pid == self.core.settings.data.active_preset)
        if dlg.exec() and dlg.action:
            getattr(self, "_do_" + dlg.action)(pid)

    def _guard(self, fn):
        try:
            return fn()
        except (ValueError, KeyError, StorageError) as e:
            choose(self.win, tr("処理できません"), str(e), [tr("閉じる")], "error")

    def _do_use(self, pid):
        p = self.core.presets.get(pid)
        self.core.settings.data.active_preset = pid
        if self._guard(lambda: self.core.settings.save() or True):
            self.win.toast.show(tr("『{0}』を使用するプリセットに設定しました。Robloxへの書き込みは『Robloxへ適用』またはプレイ時に行われます", p['name']), "ok", 5000)
            self.win.refresh_all()

    def _do_edit(self, pid):
        self.win.edit_preset(pid)

    def _do_rename(self, pid):
        p = self.core.presets.get(pid)

        def check(t):
            return check_preset_name(t) or (tr("同じ名前のプリセットが既にあります") if self.core.presets.name_exists(t, exclude=pid) else "")
        d = NameDialog(self.win, tr("名前を変更"), tr("新しい名前"), p["name"], check, tr("変更"))
        if d.exec() and self._guard(lambda: self.core.presets.rename(pid, d.value()) or True):
            self.win.toast.show(tr("名前を変更しました"), "ok"); self.win.refresh_all()

    def _do_dup(self, pid):
        if self._guard(lambda: self.core.presets.duplicate(pid) and True):
            self.win.toast.show(tr("複製しました"), "ok"); self.win.refresh_all()

    def _do_export(self, pid):
        p = self.core.presets.get(pid)
        path, _ = QFileDialog.getSaveFileName(self.win, tr("エクスポート"), safe_filename(p["name"]) + ".json", "JSON (*.json)")
        if path and self._guard(lambda: write_json(path, {k: p[k] for k in ("name", "description", "category", "flags")}, keep_bak=False) or True):
            self.win.toast.show(tr("エクスポートしました"), "ok")

    def _do_delete(self, pid):
        p = self.core.presets.get(pid)
        used = [g for g in self.core.games.games if g.preset_id == pid]
        msg = tr("プリセット『{0}』を削除しますか？（{1}フラグ。元に戻せません）", p['name'], len(p['flags']))
        if pid == self.core.settings.data.active_preset:
            msg += tr("\n\nこのプリセットは現在使用中です。削除すると使用プリセットは『なし』になります（Robloxに書き込み済みの設定ファイルは変更されません）。")
        if used:
            msg += tr("\n\n{0}件のゲームがこのプリセットを指定しています。これらは『ホームで選択中のプリセットを使う』に戻ります。", len(used))
        if choose(self.win, tr("削除の確認"), msg, [tr("削除する"), tr("キャンセル")], "warn") != 0:
            return
        if self._guard(lambda: self.core.presets.delete(pid) or True):
            s = self.core.settings.data
            if s.active_preset == pid:
                s.active_preset = ""; self.core.settings.save()
            for g in used:
                self.core.games.update(g.id, preset_id="")
            self.win.toast.show(tr("削除しました"), "ok"); self.win.refresh_all()

    # ---- 新規作成・インポート ----
    def _create_resolving(self, name, category, desc, flags):
        """同名がある場合は 上書き / 別名 / キャンセル を確認して作成する。作成/更新したIDを返す。"""
        pres = self.core.presets
        if pres.name_exists(name):
            i = choose(self.win, tr("同名のプリセットがあります"), tr("『{0}』は既に存在します。どうしますか？", name), [tr("上書きする"), tr("別名で作成する"), tr("キャンセル")], "question")
            if i == 2:
                return None
            if i == 0:
                ex = next(p for p in pres.presets if p["name"].strip().casefold() == name.casefold())
                pres.update(ex["id"], flags=flags, description=desc, category=category)
                return ex["id"]
            name = pres.unique_name(name)
        return pres.create(name, category, flags, desc)["id"]

    def new(self):
        d = NewPresetDialog(self.win)
        if d.exec():
            r = self._guard(lambda: self._create_resolving(*d.values()))
            if r:
                self.win.toast.show(tr("プリセットを作成しました"), "ok"); self.win.refresh_all()

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self.win, tr("プリセットJSONを選択"), "", tr("JSON (*.json);;すべて (*)"))
        if not path:
            return
        try:
            data, dups, errs = loads_checked(Path(path).read_text("utf-8-sig"))
        except (OSError, UnicodeDecodeError) as e:
            choose(self.win, tr("読み込めません"), str(e), [tr("閉じる")], "error"); return
        if data is None:
            TextDialog(self.win, tr("インポートできません"), tr("JSONの検証でエラーが見つかりました。"), "\n".join(errs)).exec(); return
        name, cat, desc, flags = Path(path).stem, "その他", "", data
        if isinstance(data.get("flags"), dict) and isinstance(data.get("name"), str):
            name, cat, desc, flags = data["name"], data.get("category", "その他"), data.get("description", ""), data["flags"]
        errs = validate_flags(flags)
        if errs:
            TextDialog(self.win, tr("インポートできません"), tr("フラグに問題があります。修正してから再度インポートしてください。"), "\n".join(errs[:50])).exec(); return
        if dups:
            self.win.toast.show(tr("重複キーがありました（後の値を採用）: {0}", ', '.join(dups[:5])), "warn", 5000)
        if self._guard(lambda: self._create_resolving(name, cat, desc, flags)):
            self.win.toast.show(tr("インポートしました"), "ok"); self.win.refresh_all()

    # ---- Robloxへの適用（プリセット管理とは分離） ----
    def apply_now(self):
        if not self.core.settings.data.active_preset:
            self.win.toast.show(tr("使用するプリセットを選んでください"), "warn"); return
        self.win.launch.start(None, "apply_only", self.core.settings.data.active_preset)

    def update_allow(self):
        self.win.run(self.core.allowlist.refresh_online, self._allow_ok, self._allow_err, label=tr("公式許可リストを取得中"))

    def _allow_ok(self, n):
        self.win.toast.show(tr("公式リストを更新しました（{0}件・自動抽出のため要目視確認）", n), "ok", 4500); self.win.refresh_all()

    def _allow_err(self, e):
        self.win.toast.show(str(e), "error", 6000); self.win.refresh_all()

    def load_allow(self):
        path, _ = QFileDialog.getOpenFileName(self.win, tr("許可リストのテキスト/JSON"), "", tr("テキスト/JSON (*.txt *.json *.md);;すべて (*)"))
        if path:
            try:
                n = self.core.allowlist.import_text(Path(path).read_text("utf-8-sig"), Path(path).name)
                self.win.toast.show(tr("{0}件を読み込みました（ユーザー提供ファイル）", n), "ok"); self.win.refresh_all()
            except (AllowlistError, OSError, UnicodeDecodeError) as e:
                self.win.toast.show(str(e), "error", 5000)


class PresetEditorPage(Page):
    title = N_("FastFlagsを編集")

    def __init__(self, win):
        super().__init__(win)
        self.pid, self.work, self.orig, self._loading = None, {}, {}, False
        self.name_lbl = lbl("", "h2"); self.root.addWidget(self.name_lbl)
        self.b_save = btn(tr("保存"), self.save, "primary"); self.b_as = btn(tr("別名で保存"), self.save_as)
        self.b_cancel = btn(tr("キャンセル"), self.cancel)
        self.root.addLayout(row(self.b_save, self.b_as, self.b_cancel, stretch=True))
        self.search = QLineEdit(); self.search.setPlaceholderText(tr("フラグ名・値で検索")); self.search.textChanged.connect(self.refresh)
        self.root.addWidget(self.search)
        self.table = make_table([tr("フラグ名"), tr("値"), tr("型"), tr("公式許可リスト"), ""], [330, 170, 70, 230, 56])
        self.table.setSelectionMode(QAbstractItemView.SingleSelection); self.table.setMinimumHeight(300)
        self.table.itemChanged.connect(self._changed); self.root.addWidget(self.table, 1)
        self.n_in, self.v_in = QLineEdit(), QLineEdit()
        self.n_in.setPlaceholderText(tr("フラグ名（例: FFlagExample）")); self.v_in.setPlaceholderText(tr('値（true / 12 / "文字列"）'))
        self.v_in.returnPressed.connect(self.add); self.n_in.returnPressed.connect(self.v_in.setFocus)
        a = QHBoxLayout(); a.setSpacing(8); a.addWidget(self.n_in, 3); a.addWidget(self.v_in, 2); a.addWidget(btn(tr("＋ 追加"), self.add, "primary")); self.root.addLayout(a)
        self.root.addLayout(row(btn(tr("JSONインポート"), self.import_), btn(tr("JSONエクスポート"), self.export), stretch=True))
        self.msg = lbl("", None); self.root.addWidget(self.msg)
        self.hint = lbl(tr("公式許可リストに無いフラグはRobloxに無視される可能性があります。保存はこのアプリ内のプリセットへの保存であり、Robloxへの適用ではありません。"), "muted")
        self.root.addWidget(self.hint)

    # ---- 状態 ----
    def dirty(self) -> bool:
        return self.pid is not None and json.dumps(self.work, ensure_ascii=False) != json.dumps(self.orig, ensure_ascii=False)

    def open(self, pid):
        p = self.core.presets.get(pid)
        if p is None:
            return False
        self.pid, self.work, self.orig = pid, copy.deepcopy(p["flags"]), copy.deepcopy(p["flags"])
        self.search.clear(); self.refresh(); return True

    def can_leave(self) -> bool:
        if not self.dirty():
            return True
        ok = choose(self.win, tr("未保存の変更"), tr("編集中の変更はまだ保存されていません。破棄して移動しますか？"), [tr("変更を破棄して移動"), tr("編集を続ける")], "warn") == 0
        if ok:
            self.work = copy.deepcopy(self.orig)
        return ok

    def refresh(self, *_):
        p = self.core.presets.get(self.pid) if self.pid else None
        if self.pid and p is None:
            self.pid = None
        self._loading = True
        self.name_lbl.setText(tr("編集中: {0}{1}", p['name'], ' *' if self.dirty() else '') if p else tr("（プリセットが選択されていません）"))
        self.b_cancel.setText(tr("キャンセル") if self.dirty() else tr("閉じる"))
        for b in (self.b_save, self.b_as): b.setEnabled(p is not None)
        q = self.search.text().strip().lower()
        self.table.setRowCount(0)
        for name, val in self.work.items():
            if q and q not in name.lower() and q not in str(val).lower():
                continue
            r = self.table.rowCount(); self.table.insertRow(r)
            bad = validate_flag(name, val)
            vals = [name, json.dumps(val, ensure_ascii=False) if value_type(val) != "invalid" else repr(val), value_type(val),
                    tr(ALLOW_TEXT[self.core.allowlist.status(name)])]
            for c, t in enumerate(vals):
                it = QTableWidgetItem(t); it.setData(UR, name)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | (Qt.ItemIsEditable if c < 2 else Qt.NoItemFlags))
                if bad:
                    it.setForeground(Qt.red); it.setToolTip("\n".join(bad))
                self.table.setItem(r, c, it)
            d = AnimButton("✕", "ghost"); d.setMinimumHeight(28); d.setToolTip(tr("このフラグを削除"))
            d.clicked.connect(lambda _=False, n=name: self._del(n)); self.table.setCellWidget(r, 4, d)
            self.table.setRowHeight(r, 38)
        self._loading = False
        errs = validate_flags(self.work)
        self.msg.setText(tr("<span style='color:{0}'>✔ 検証OK（{1}件）</span>", OK, len(self.work)) if not errs else
                         tr("<span style='color:{0}'>✖ {1}件の問題があります（保存できません）:</span><br>", ERR, len(errs)) + "<br>".join(errs[:5]))

    # ---- 編集 ----
    def _changed(self, item):
        if self._loading:
            return
        old, col, text = item.data(UR), item.column(), item.text()
        try:
            if col == 0:
                new = text.strip()
                bad = validate_flag(new, self.work[old])
                if bad:
                    raise ValueError("; ".join(bad))
                if new != old:
                    if new in self.work:
                        raise ValueError(tr("{0} は既に存在します", new))
                    self.work = {(new if k == old else k): v for k, v in self.work.items()}
            elif col == 1:
                v = parse_value_text(text)
                bad = validate_flag(old, v)
                if bad:
                    raise ValueError("; ".join(bad))
                self.work[old] = v
        except ValueError as e:
            self.win.toast.show(tr("変更できません: {0}", e), "error", 5000)
        QTimer.singleShot(0, self.refresh)

    def _del(self, name):
        self.work.pop(name, None); self.refresh()

    def add(self):
        name = self.n_in.text().strip()
        try:
            v = parse_value_text(self.v_in.text())
            bad = validate_flag(name, v)
            if bad:
                raise ValueError("; ".join(bad))
            if name in self.work:
                raise ValueError(tr("{0} は既に存在します", name))
        except ValueError as e:
            self.msg.setText(f"<span style='color:{ERR}'>✖ {e}</span>"); return
        self.work[name] = v; self.n_in.clear(); self.v_in.clear(); self.n_in.setFocus(); self.refresh()
        self.table.scrollToBottom()
        if self.core.allowlist.status(name) != "allowed":
            self.win.toast.show(tr("追加しました（公式リストで確認できないため、Robloxに無視される可能性があります）"), "warn", 4500)

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self.win, tr("FastFlag JSONを選択"), "", tr("JSON (*.json);;すべて (*)"))
        if not path:
            return
        try:
            data, dups, errs = loads_checked(Path(path).read_text("utf-8-sig"))
        except (OSError, UnicodeDecodeError) as e:
            choose(self.win, tr("読み込めません"), str(e), [tr("閉じる")], "error"); return
        if data is not None and isinstance(data.get("flags"), dict) and isinstance(data.get("name"), str):
            data = data["flags"]; errs = validate_flags(data)
        if data is None or errs:
            TextDialog(self.win, tr("インポートできません"), tr("JSONの検証でエラーが見つかりました。内容は変更されていません。"), "\n".join(errs[:50])).exec(); return
        msg = tr("{0}件のフラグを読み込みます。", len(data)) + (tr("\n⚠ 重複キー（後の値を採用）: {0}", ', '.join(dups[:10])) if dups else "")
        i = choose(self.win, tr("インポート"), msg, [tr("追加/更新"), tr("すべて置き換え"), tr("キャンセル")], "question")
        if i == 0:
            self.work.update(data)
        elif i == 1:
            self.work = dict(data)
        if i < 2:
            self.refresh(); self.win.toast.show(tr("編集中の内容へ読み込みました（保存するまで反映されません）"), "ok", 4000)

    def export(self):
        i = choose(self.win, tr("エクスポート"), tr("形式を選択してください。"), [tr("Roblox形式（ClientAppSettings.json）"), tr("そのままのJSON"), tr("キャンセル")])
        if i == 2:
            return
        path, _ = QFileDialog.getSaveFileName(self.win, tr("保存先"), "ClientAppSettings.json" if i == 0 else "flags.json", "JSON (*.json)")
        if not path:
            return
        try:
            write_json(path, to_roblox_payload(self.work, self.core.settings.data.value_format) if i == 0 else self.work, keep_bak=False)
            self.win.toast.show(tr("エクスポートしました"), "ok")
        except StorageError as e:
            choose(self.win, tr("保存できません"), str(e), [tr("閉じる")], "error")

    # ---- 保存・キャンセル ----
    def _check(self) -> bool:
        errs = validate_flags(self.work)
        if errs:
            TextDialog(self.win, tr("保存できません"), tr("不正なフラグがあるため保存できません。修正または削除してください。"), "\n".join(errs[:50])).exec()
        return not errs

    def save(self):
        if self.pid is None or not self._check():
            return
        try:
            self.core.presets.update(self.pid, flags=dict(self.work))
        except (ValueError, KeyError, StorageError) as e:
            choose(self.win, tr("保存できません"), tr("{0}\n\n編集内容はこの画面に残っています。権限・空き容量を確認して再試行してください。", e), [tr("閉じる")], "error"); return
        self.orig = copy.deepcopy(self.work)
        self.win.toast.show(tr("プリセットを保存しました（アプリ内への保存です。Robloxへの適用は別操作です）"), "ok", 4500)
        self.win.refresh_all()

    def save_as(self):
        if self.pid is None or not self._check():
            return
        base = self.core.presets.get(self.pid)

        def check(t):
            return check_preset_name(t) or (tr("同じ名前のプリセットが既にあります") if self.core.presets.name_exists(t) else "")
        d = NameDialog(self.win, tr("別名で保存"), tr("新しいプリセット名"), self.core.presets.unique_name(base["name"] + " (copy)"), check, tr("保存"))
        if not d.exec():
            return
        try:
            p = self.core.presets.create(d.value(), base["category"], dict(self.work), base.get("description", ""))
        except (ValueError, StorageError) as e:
            choose(self.win, tr("保存できません"), str(e), [tr("閉じる")], "error"); return
        self.work = copy.deepcopy(self.orig)       # 元のプリセットは未変更のまま
        self.open(p["id"]); self.win.toast.show(tr("別名で保存しました"), "ok"); self.win.refresh_all()

    def cancel(self):
        if self.dirty() and choose(self.win, tr("未保存の変更"), tr("変更を破棄して一覧へ戻りますか？"), [tr("変更を破棄"), tr("編集を続ける")], "warn") != 0:
            return
        self.work = copy.deepcopy(self.orig)         # 未保存の変更は元データへ一切反映しない
        self.win.goto("flags")
