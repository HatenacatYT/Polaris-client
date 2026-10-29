"""FastFlagをRobloxのClientAppSettings.jsonへ安全に適用する。"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .backup import BackupManager
from .flags import validate_flags, to_roblox_payload
from .jsonio import write_json, StorageError
from .roblox import RobloxInstall, client_settings_path

log = logging.getLogger("polaris.apply")


@dataclass
class ApplyResult:
    ok: bool
    message: str
    path: Path | None = None
    backup_id: str = ""
    rolled_back: bool = False


def _within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def apply_flags(backups: BackupManager, install: RobloxInstall, flags: dict, fmt: str = "string") -> ApplyResult:
    errs = validate_flags(flags)
    if errs:
        return ApplyResult(False, "設定の検証に失敗しました:\n" + "\n".join(errs[:10]))
    target = client_settings_path(install)
    if not _within(target, install.version_dir) or not install.version_dir.is_dir():
        return ApplyResult(False, f"適用先が不正、または存在しません: {target}")
    payload = to_roblox_payload(flags, fmt)
    existed = target.exists()
    bid = ""
    try:
        if existed:
            bid = backups.create("roblox", "FastFlag適用前", [target]).id
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json(target, payload, keep_bak=False)
        if json.loads(target.read_text("utf-8")) != payload:
            raise StorageError("書き込み後の再読み込み検証に失敗しました")
    except (StorageError, OSError, ValueError) as e:
        rolled = False
        try:
            if bid:
                backups.restore(bid)
                rolled = True
            elif not existed and target.exists():
                target.unlink()   # 今回新規作成した自分のファイルのみ取り消す
                rolled = True
        except Exception as e2:  # noqa
            log.error("ロールバック失敗: %s", e2)
        log.error("apply_failed path=%s error=%s rolled_back=%s", target, e, rolled)
        return ApplyResult(False, f"適用に失敗しました: {e}" + ("\n元の状態に戻しました。" if rolled else ""), target, bid, rolled)
    log.info("apply_ok path=%s flags=%d backup=%s", target, len(payload), bid)
    return ApplyResult(True, f"{len(payload)}件を書き込みました（Roblox側で実際に反映されたかは未確認）", target, bid)
