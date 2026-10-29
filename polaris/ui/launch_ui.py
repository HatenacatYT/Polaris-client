"""起動・適用フローのGUI制御（確認ダイアログ、失敗時の選択肢）。"""
from __future__ import annotations
import logging

from PySide6.QtWidgets import QInputDialog

from ..core.launcher import LaunchPlan, LaunchResult
from .dialogs import choose, steps_text, TextDialog

log = logging.getLogger("polaris.launchui")


class LaunchController:
    def __init__(self, win):
        self.win, self.busy = win, False

    @property
    def core(self): return self.win.core

    def start(self, game, mode, preset_id=None):
        if self.busy:
            self.win.toast.show("別の起動処理を実行中です", "warn"); return
        self.busy = True
        self.win.run(self.core.launcher.prepare, lambda p: self._prepared(p, game, mode, preset_id), self._crash,
                     game, mode, preset_id, label="Roblox環境を確認中")

    def _crash(self, e):
        self.busy = False
        log.error("launch_crash %s", e)
        self.win.set_result(f"予期しないエラー: {e}")
        choose(self.win, "エラー", f"予期しないエラーが発生しました:\n{e}", ["閉じる"], "error")

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
                warn = ("\n\n⚠ 次のフラグは公式許可リストで掲載を確認できません。書き込まれても Roblox に無視される可能性があります:\n  " +
                        ", ".join(plan.unverified[:15]) + ("…" if len(plan.unverified) > 15 else ""))
            if plan.note:
                warn += "\n\n⚠ " + plan.note
            body = (f"適用先: {plan.target}\nRoblox環境: {plan.install.version_name}（{plan.install.verified_by}）\n\n"
                    f"変更内容（このファイルはRobloxに適用する設定で置き換えられます）:\n{plan.diff.to_text()}{warn}")
            labels = ["適用して続行"] + (["適用せずに起動"] if mode != "apply_only" else []) + ["キャンセル"]
            if mode != "apply_only":
                # 3択: 適用して続行 / 適用せずに起動 / キャンセル
                idx = choose(self.win, "適用前の確認", "ClientAppSettings.json を書き換えます。詳細を確認して選択してください。",
                             labels, "question", detail=body)
                if idx == 2:
                    self.busy = False; return
                apply = (idx == 0)
            else:
                box = TextDialog(self.win, "適用前の確認", "ファイルを書き換える前に内容を確認してください。適用前に既存ファイルはバックアップされます。",
                                 body, ok=labels[0], cancel=labels[-1])
                if box.exec() != TextDialog.Accepted:
                    self.busy = False; return
        self.win.run(self.core.launcher.execute, lambda r: self._done(r, plan, game, mode, preset_id), self._crash,
                     plan, apply, label="設定を適用して起動中" if plan.apply_needed else "起動要求を送信中")

    def _done(self, r: LaunchResult, plan, game, mode, preset_id):
        self.busy = False
        self.win.set_result(r.message + "\n\n" + steps_text(r.steps))
        self.win.refresh_all()
        if r.ok:
            self.win.toast.show(r.message if len(r.message) < 70 else "起動要求を送信しました（接続の成否は未確認）", "ok", 4500)
            if r.code == "APPLIED":
                self.win.toast.show("FastFlagを書き込みました", "ok")
            return
        self._failure(r.code, r.message, [], game, mode, preset_id, steps=r.steps)

    def _failure(self, code, msg, candidates, game, mode, preset_id, steps=None):
        detail = steps_text(steps) if steps else ""
        if code == "AMBIGUOUS" and candidates:
            names = [str(c) for c in candidates]
            item, ok = QInputDialog.getItem(self.win, "Roblox環境の選択", msg + "\n\n使用する環境を選択:", names, 0, False)
            if ok and item:
                self.core.settings.data.pinned_version_dir = item
                self.core.settings.save()
                self.win.redetect(lambda: self.start(game, mode, preset_id))
            return
        if code == "APPLY_FAILED":
            i = choose(self.win, "FastFlagの適用に失敗", msg + "\n\nどうしますか？", ["適用せずに起動", "再試行", "閉じる"], "error", detail)
            if i == 0 and mode == "apply_and_play":
                self.start(game, "play_only")
            elif i == 1:
                self.start(game, mode, preset_id)
            return
        if code in ("NOT_FOUND", "ERROR"):
            i = choose(self.win, "Robloxを検出できません", msg, ["再検出して再試行", "閉じる"], "error", detail)
            if i == 0:
                self.win.redetect(lambda: self.start(game, mode, preset_id))
            return
        if code == "URI_FAILED":
            i = choose(self.win, "ゲームの起動要求に失敗", msg, ["再試行", "Robloxのみ通常起動", "閉じる"], "error", detail)
            if i == 0:
                self.start(game, "play_only")
            elif i == 1:
                self.start(None, "roblox_only")
            return
        choose(self.win, "起動できません", msg, ["閉じる"], "error", detail)
