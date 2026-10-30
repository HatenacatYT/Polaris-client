"""起動・適用フローのGUI制御（確認ダイアログ、失敗時の選択肢）。"""
from __future__ import annotations
from ..core.i18n import tr, N_
import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QInputDialog

from ..core.launcher import LaunchPlan, LaunchResult
from .dialogs import choose, steps_text, TextDialog

log = logging.getLogger("polaris.launchui")


class LaunchController(QObject):
    busy_changed = Signal(bool)

    def __init__(self, win):
        super().__init__(win)
        self.win, self._busy = win, False

    @property
    def busy(self) -> bool:
        return self._busy

    @busy.setter
    def busy(self, v: bool):
        if v != self._busy:
            self._busy = v
            self.busy_changed.emit(v)

    @property
    def core(self): return self.win.core

    def start(self, game, mode, preset_id=None):
        if self.busy:
            self.win.toast.show(tr("別の起動処理を実行中です"), "warn"); return
        self.busy = True
        self.win.run(self.core.launcher.prepare, lambda p: self._prepared(p, game, mode, preset_id), self._crash,
                     game, mode, preset_id, label=tr("Roblox環境を確認中"))

    def _crash(self, e):
        self.busy = False
        log.error("launch_crash %s", e)
        self.win.set_result(tr("予期しないエラー: {0}", e))
        choose(self.win, tr("エラー"), tr("予期しないエラーが発生しました:\n{0}", e), [tr("閉じる")], "error")

    def _prepared(self, plan: LaunchPlan, game, mode, preset_id):
        if not plan.ok:
            self.busy = False
            self.win.set_result(steps_text(plan.steps))
            self._failure(plan.error_code, plan.error, plan.candidates, game, mode, preset_id)
            return
        apply = None
        if plan.apply_needed and self.core.settings.data.confirm_before_apply:
            warn = ""
            if plan.unverified:
                warn = (tr("\n\n⚠ 次のフラグは公式許可リストで掲載を確認できません。書き込まれても Roblox に無視される可能性があります:\n  ") +
                        ", ".join(plan.unverified[:15]) + ("…" if len(plan.unverified) > 15 else ""))
            if plan.note:
                warn += "\n\n⚠ " + plan.note
            body = (tr("適用先: {0}\nRoblox環境: {1}（{2}）\n\n変更内容（このファイルはRobloxに適用する設定で置き換えられます）:\n{3}{4}", plan.target, plan.install.version_name, plan.install.verified_by, plan.diff.to_text(), warn))
            labels = [tr("適用して続行")] + ([tr("適用せずに起動")] if mode != "apply_only" else []) + [tr("キャンセル")]
            if mode != "apply_only":
                # 3択: 適用して続行 / 適用せずに起動 / キャンセル
                idx = choose(self.win, tr("適用前の確認"), tr("ClientAppSettings.json を書き換えます。詳細を確認して選択してください。"),
                             labels, "question", detail=body)
                if idx == 2:
                    self.busy = False; return
                apply = (idx == 0)
            else:
                box = TextDialog(self.win, tr("適用前の確認"), tr("ファイルを書き換える前に内容を確認してください。適用前に既存ファイルはバックアップされます。"),
                                 body, ok=labels[0], cancel=labels[-1])
                if box.exec() != TextDialog.Accepted:
                    self.busy = False; return
        self.win.run(self.core.launcher.execute, lambda r: self._done(r, plan, game, mode, preset_id), self._crash,
                     plan, apply, label=tr("設定を適用して起動中") if plan.apply_needed else tr("起動要求を送信中"))

    def _done(self, r: LaunchResult, plan, game, mode, preset_id):
        self.busy = False
        self.win.set_result(r.message + "\n\n" + steps_text(r.steps))
        self.win.refresh_all()
        if r.ok:
            self.win.toast.show(r.message if len(r.message) < 70 else tr("起動要求を送信しました（接続の成否は未確認）"), "ok", 4500)
            if r.code == "APPLIED":
                self.win.toast.show(tr("FastFlagを書き込みました"), "ok")
            return
        self._failure(r.code, r.message, [], game, mode, preset_id, steps=r.steps)

    def _failure(self, code, msg, candidates, game, mode, preset_id, steps=None):
        detail = steps_text(steps) if steps else ""
        if code == "AMBIGUOUS" and candidates:
            names = [str(c) for c in candidates]
            item, ok = QInputDialog.getItem(self.win, tr("Roblox環境の選択"), msg + tr("\n\n使用する環境を選択:"), names, 0, False)
            if ok and item:
                self.core.settings.data.pinned_version_dir = item
                self.core.settings.save()
                self.win.redetect(lambda: self.start(game, mode, preset_id))
            return
        if code == "APPLY_FAILED":
            i = choose(self.win, tr("FastFlagの適用に失敗"), msg + tr("\n\nどうしますか？"), [tr("適用せずに起動"), tr("再試行"), tr("閉じる")], "error", detail)
            if i == 0 and mode == "apply_and_play":
                self.start(game, "play_only")
            elif i == 1:
                self.start(game, mode, preset_id)
            return
        if code in ("NOT_FOUND", "ERROR"):
            i = choose(self.win, tr("Robloxを検出できません"), msg, [tr("再検出して再試行"), tr("閉じる")], "error", detail)
            if i == 0:
                self.win.redetect(lambda: self.start(game, mode, preset_id))
            return
        if code == "URI_FAILED":
            i = choose(self.win, tr("ゲームの起動要求に失敗"), msg, [tr("再試行"), tr("Robloxのみ通常起動"), tr("閉じる")], "error", detail)
            if i == 0:
                self.start(game, "play_only")
            elif i == 1:
                self.start(None, "roblox_only")
            return
        choose(self.win, tr("起動できません"), msg, [tr("閉じる")], "error", detail)
