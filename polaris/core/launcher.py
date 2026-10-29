"""起動フロー: prepare(検証・差分算出) → execute(バックアップ・適用・起動要求)。"""
from __future__ import annotations
import json
import logging
import os
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .applier import apply_flags
from .flags import validate_flags, to_roblox_payload, diff_payload, FlagDiff
from .games import Game, validate_place_id, build_launch_uri, uri_place_id, now_iso, InvalidPlace
from .roblox import RobloxInstall, client_settings_path, roblox_process_running

log = logging.getLogger("polaris.launch")
MODES = ("apply_and_play", "play_only", "roblox_only", "apply_only")


@dataclass
class Step:
    name: str
    status: str  # ok / warn / fail / skip
    detail: str = ""


@dataclass
class LaunchPlan:
    mode: str
    game: Game | None = None
    install: RobloxInstall | None = None
    uri: str = ""
    preset_id: str = ""
    flags: dict = field(default_factory=dict)
    apply_needed: bool = False
    unverified: list = field(default_factory=list)
    diff: FlagDiff | None = None
    target: Path | None = None
    steps: list = field(default_factory=list)
    error_code: str = ""
    error: str = ""
    candidates: list = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return not self.error_code

    def fail(self, code, msg, step="検証"):
        self.error_code, self.error = code, msg
        self.steps.append(Step(step, "fail", msg))
        log.error("launch_prepare_failed code=%s msg=%s", code, msg)
        return self


@dataclass
class LaunchResult:
    ok: bool
    code: str
    message: str
    steps: list
    applied: bool = False
    process_seen: bool = False
    uri: str = ""


def _open_uri(uri: str):
    if os.name != "nt":
        raise OSError("Windows以外ではRobloxを起動できません")
    os.startfile(uri)  # type: ignore[attr-defined]  # 登録済みのroblox://ハンドラへ委譲


def _open_exe(path: Path):
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(path)], cwd=str(path.parent), creationflags=flags, close_fds=True)


def _net_check() -> bool:
    try:
        socket.create_connection(("www.roblox.com", 443), timeout=3).close()
        return True
    except OSError:
        return False


class Launcher:
    def __init__(self, core, open_uri=_open_uri, open_exe=_open_exe, process_running=roblox_process_running,
                 net_check=_net_check, sleep=time.sleep, poll_seconds=15):
        self.core, self.open_uri, self.open_exe = core, open_uri, open_exe
        self.process_running, self.net_check, self.sleep, self.poll_seconds = process_running, net_check, sleep, poll_seconds

    def _read_existing(self, target: Path, plan: LaunchPlan) -> dict:
        if not target.exists():
            return {}
        try:
            d = json.loads(target.read_text("utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            plan.note = "既存のClientAppSettings.jsonが読めません（バックアップ後に置き換えます）"
            return {}

    def prepare(self, game: Game | None, mode: str, preset_id: str | None = None) -> LaunchPlan:
        c = self.core
        plan = LaunchPlan(mode=mode, game=game)
        log.info("launch_prepare mode=%s game=%s", mode, game.place_id if game else None)
        if mode not in MODES:
            return plan.fail("BAD_MODE", f"不明な起動モード: {mode}")
        if mode in ("apply_and_play", "play_only"):
            if game is None:
                return plan.fail("INVALID_PLACE", "ゲームが選択されていません")
            try:
                pid = validate_place_id(game.place_id)
                plan.uri = build_launch_uri(pid)
                if uri_place_id(plan.uri) != pid:
                    raise InvalidPlace("URIへのPlace ID埋め込み検証に失敗")
            except InvalidPlace as e:
                return plan.fail("INVALID_PLACE", str(e))
            plan.steps.append(Step("Place IDの検証", "ok", f"placeId={pid}"))
        det = c.detect_outcome()
        if det.install is None:
            plan.candidates = det.candidates
            return plan.fail(det.code, det.message, "Roblox環境の検出")
        plan.install = det.install
        plan.steps.append(Step("Roblox環境の検出", "ok", f"{det.install.version_name}（{det.install.verified_by}）"))
        wants_apply = mode == "apply_only" or (mode == "apply_and_play" and game is not None and game.apply_flags)
        if not wants_apply:
            plan.steps.append(Step("FastFlag適用", "skip", "適用せずに起動します"))
            return plan
        pid_ = preset_id if preset_id is not None else ((game.preset_id if game else "") or c.settings.data.active_preset)
        plan.preset_id = pid_
        if not pid_:
            if mode == "apply_only":
                return plan.fail("NO_PRESET", "適用するプリセットが選択されていません")
            plan.steps.append(Step("FastFlag適用", "skip", "プリセット未選択のため適用しません"))
            return plan
        try:
            plan.flags = c.resolve_flags(pid_)
        except KeyError:
            return plan.fail("PRESET_MISSING", "選択されたプリセットが見つかりません（削除された可能性）")
        if not plan.flags:
            if mode == "apply_only":
                return plan.fail("NOTHING_TO_APPLY", "適用対象の（有効な）フラグがありません")
            plan.steps.append(Step("FastFlag適用", "skip", "選択された設定が空です"))
            return plan
        errs = validate_flags(plan.flags)
        if errs:
            return plan.fail("INVALID_FLAGS", "\n".join(errs[:10]), "設定の検証")
        plan.steps.append(Step("設定の検証", "ok", f"{len(plan.flags)}件"))
        plan.unverified = [n for n in plan.flags if c.allowlist.status(n) != "allowed"]
        if plan.unverified:
            plan.steps.append(Step("公式許可リスト", "warn", f"{len(plan.unverified)}件は公式掲載を確認できず、反映されない可能性があります"))
        payload = to_roblox_payload(plan.flags, c.settings.data.value_format)
        plan.target = client_settings_path(plan.install)
        plan.diff = diff_payload(self._read_existing(plan.target, plan), payload)
        plan.apply_needed = True
        return plan

    def execute(self, plan: LaunchPlan, apply: bool | None = None) -> LaunchResult:
        c = self.core
        steps = list(plan.steps)
        if not plan.ok:
            return LaunchResult(False, plan.error_code, plan.error, steps)
        do_apply = plan.apply_needed if apply is None else (apply and plan.apply_needed)
        det = c.detect_outcome()           # 起動直前に再確認（更新による場所の変化に追従）
        if det.install is None:
            steps.append(Step("起動前の再検出", "fail", det.message))
            return LaunchResult(False, det.code, det.message, steps)
        if plan.install and det.install.version_dir != plan.install.version_dir:
            log.info("roblox_version_changed_before_launch old=%s new=%s", plan.install.version_dir, det.install.version_dir)
            steps.append(Step("起動前の再検出", "warn", f"環境が変わりました → {det.install.version_name}"))
        else:
            steps.append(Step("起動前の再検出", "ok", det.install.version_name))
        plan.install = det.install
        applied = False
        ar_msg = "適用しませんでした"
        if do_apply:
            ar = apply_flags(c.backups, plan.install, plan.flags, c.settings.data.value_format)
            c.record_apply(ar, plan)
            if not ar.ok:
                steps.append(Step("FastFlagの適用", "fail", ar.message))
                return LaunchResult(False, "APPLY_FAILED", ar.message, steps)
            applied = True
            ar_msg = ar.message
            steps.append(Step("バックアップ", "ok", "適用前に既存設定を退避しました" if ar.backup_id else "既存設定なし（新規作成）"))
            steps.append(Step("FastFlagの適用", "warn" if plan.unverified else "ok",
                              ar.message + (f"／未確認フラグ{len(plan.unverified)}件" if plan.unverified else "")))
            c.maybe_prune_backups()
        else:
            steps.append(Step("FastFlagの適用", "skip", "実行しません"))
        if plan.mode == "apply_only":
            return LaunchResult(True, "APPLIED", ar_msg, steps, applied=applied)
        if not self.net_check():
            steps.append(Step("ネットワーク確認", "warn", "www.roblox.com に接続できません。オフライン/障害の場合、ゲームへ参加できません"))
        was_running = self.process_running()
        try:
            if plan.mode == "roblox_only":
                if plan.install.launcher_exe is None:
                    raise OSError("RobloxPlayerLauncher.exe が見つかりません")
                self.open_exe(plan.install.launcher_exe)
                what = "Roblox本体の起動要求"
            else:
                if plan.game is None or uri_place_id(plan.uri) != plan.game.place_id:
                    raise InvalidPlace("起動URIのPlace IDがゲーム設定と一致しません")
                self.open_uri(plan.uri)
                what = f"ゲーム起動要求 (placeId={plan.game.place_id})"
        except InvalidPlace as e:
            steps.append(Step("起動要求の送信", "fail", str(e)))
            return LaunchResult(False, "INVALID_PLACE", str(e), steps, applied, uri=plan.uri)
        except Exception as e:
            msg = f"起動要求を処理できませんでした（Robloxが未登録/URIハンドラ異常の可能性）: {e}"
            log.error("launch_failed %s", e)
            steps.append(Step("起動要求の送信", "fail", msg))
            return LaunchResult(False, "URI_FAILED", msg, steps, applied, uri=plan.uri)
        log.info("launch_requested mode=%s place=%s", plan.mode, plan.game.place_id if plan.game else None)
        steps.append(Step("起動要求の送信", "ok", what))
        if plan.game:
            c.games.record_launch(plan.game.id)
            c.state.set("last_game", {"id": plan.game.id, "name": plan.game.name, "place_id": plan.game.place_id, "at": now_iso()})
        seen = False
        if plan.game is None or plan.game.verify_process:
            for _ in range(self.poll_seconds):
                if self.process_running():
                    seen = True
                    break
                self.sleep(1)
        if seen:
            steps.append(Step("Robloxプロセス確認", "ok", "起動前から実行中でした" if was_running else "プロセスを検出しました"))
        else:
            steps.append(Step("Robloxプロセス確認", "warn", "プロセスを確認できません（起動中・ログイン待ち・更新中の可能性）"))
        msg = ("起動要求を送信しました。" + ("Robloxのプロセスは検出しました。" if seen else "") +
               "ゲームへ実際に接続できたかは、ランチャーからは確認できません。")
        return LaunchResult(True, "REQUEST_SENT", msg, steps, applied, seen, plan.uri)
