"""サービスの集約（GUI非依存・テスト可能）。"""
from __future__ import annotations
import logging
import platform
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import __version__
from .allowlist import AllowlistStore
from .backup import BackupManager
from .flags import FlagStore, PresetStore, EDITOR_PRESET_ID
from .games import GameLibrary
from .launcher import Launcher
from .logsetup import setup_logging, MEMORY, anonymize
from .paths import AppPaths
from .roblox import Detector, RobloxInstall, RobloxNotFound, RobloxAmbiguous
from .store import SettingsStore, StateStore

log = logging.getLogger("polaris.core")


@dataclass
class Detection:
    install: RobloxInstall | None = None
    code: str = ""
    message: str = ""
    candidates: list = field(default_factory=list)


class Core:
    def __init__(self, paths: AppPaths | None = None, *, detector=None, launcher_kwargs=None):
        self.paths = paths or AppPaths.default()
        setup_logging(self.paths.logs)
        log.info("app_start version=%s python=%s os=%s", __version__, platform.python_version(), platform.platform())
        self.settings = SettingsStore(self.paths.settings_file)
        self.state = StateStore(self.paths.state_file)
        self.flags = FlagStore(self.paths.flags_file)
        self.presets = PresetStore(self.paths.presets_file)
        self.games = GameLibrary(self.paths.games_file)
        self.allowlist = AllowlistStore(self.paths.allowlist_file)
        self.backups = BackupManager(self.backup_dir)
        self.detector = detector or Detector(pinned_fn=lambda: self.settings.data.pinned_version_dir)
        self.launcher = Launcher(self, **(launcher_kwargs or {}))
        self.last_detection = Detection(code="NOT_CHECKED", message="未確認")

    def backup_dir(self) -> Path:
        d = self.settings.data.backup_dir
        return Path(d) if d else self.paths.default_backups

    def app_data_files(self) -> list[Path]:
        p = self.paths
        return [f for f in (p.flags_file, p.presets_file, p.games_file, p.settings_file) if f.is_file()]

    def reload_all(self):
        self.settings.load(); self.flags.load(); self.presets.load(); self.games.load()

    def resolve_flags(self, preset_id: str) -> dict:
        if preset_id == EDITOR_PRESET_ID:
            return self.flags.enabled_dict()
        p = self.presets.get(preset_id)
        if p is None:
            raise KeyError(preset_id)
        return dict(p["flags"])

    def preset_choices(self) -> list[tuple[str, str]]:
        return [("", "（適用しない）"), (EDITOR_PRESET_ID, "エディターの現在の設定")] + \
               [(p["id"], f"{p['name']}［{p['category']}］") for p in self.presets.presets]

    def detect_outcome(self, use_network: bool = True) -> Detection:
        try:
            d = Detection(install=self.detector.detect(use_network))
        except RobloxNotFound as e:
            d = Detection(code="NOT_FOUND", message=str(e))
        except RobloxAmbiguous as e:
            d = Detection(code="AMBIGUOUS", message=str(e), candidates=e.candidates)
        except Exception as e:  # noqa  検出中の予期しない例外でも落とさない
            log.exception("detect_error")
            d = Detection(code="ERROR", message=f"検出中にエラーが発生しました: {e}")
        new = str(d.install.version_dir) if d.install else ""
        old = self.state.get("last_detected_dir", "")
        if d.install and old and old != new:
            log.info("roblox_version_changed old=%s new=%s", old, new)
        if d.install and old != new:
            self.state.set("last_detected_dir", new)
        self.last_detection = d
        return d

    def record_apply(self, ar, plan):
        self.state.set("last_apply", {
            "at": datetime.now().isoformat(timespec="seconds"), "ok": ar.ok, "message": ar.message,
            "path": str(ar.path or ""), "version": plan.install.version_name if plan.install else "",
            "version_dir": str(plan.install.version_dir) if plan.install else "",
            "count": len(plan.flags), "unverified": len(plan.unverified), "preset": plan.preset_id})

    def needs_reapply(self) -> bool:
        la, inst = self.state.get("last_apply"), self.last_detection.install
        return bool(la and la.get("ok") and inst and la.get("version_dir") != str(inst.version_dir))

    def maybe_prune_backups(self):
        s = self.settings.data
        if s.backup_auto_prune:
            self.backups.prune(s.backup_max_count, s.backup_max_days)

    def diagnostics_text(self) -> str:
        d = self.last_detection
        lines = [f"Polaris {__version__}", f"Python {platform.python_version()} / {platform.platform()}",
                 f"時刻: {datetime.now().isoformat(timespec='seconds')}",
                 f"Roblox検出: {'OK ' + str(d.install.version_dir) + ' (' + d.install.verified_by + ')' if d.install else d.code + ' ' + d.message}",
                 f"許可リスト: {self.allowlist.state_text()}",
                 f"フラグ数: {len(self.flags.flags)} / プリセット数: {len(self.presets.presets)} / ゲーム数: {len(self.games.games)}",
                 f"最後の適用: {self.state.get('last_apply')}", "", "---- ログ ----", *MEMORY.lines]
        return anonymize("\n".join(lines))

    def export_diagnostics(self, dest: Path) -> Path:
        dest = Path(dest)
        dest.write_text(self.diagnostics_text(), encoding="utf-8")
        log.info("diagnostics_exported")
        return dest

    def shutdown(self):
        log.info("app_exit")
