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
from .i18n import set_language, tr, N_
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
        self._early_language()
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
        self.last_detection = Detection(code="NOT_CHECKED", message=tr("未確認"))
        set_language(self.settings.data.language)
        self._migrate_editor_flags()

    def _early_language(self):
        """設定読込中のメッセージも正しい言語になるよう、先に言語だけ読む。"""
        import json
        try:
            set_language(json.loads(self.paths.settings_file.read_text("utf-8")).get("language", "ja"))
        except (OSError, ValueError, AttributeError):
            set_language("ja")

    def _migrate_editor_flags(self):
        """旧バージョンの『エディター』のフラグをプリセットへ移行する（元ファイルは残す）。"""
        if self.state.get("migrated_v2"):
            return
        try:
            new_id = ""
            if self.flags.flags:
                p = self.presets.create(self.presets.unique_name(tr("移行: 以前のエディター設定")), "その他",
                                        {n: f.value for n, f in self.flags.flags.items()},
                                        tr("旧バージョンのFastFlagエディターから移行"))
                new_id = p["id"]
            if self.settings.data.active_preset == EDITOR_PRESET_ID:
                self.settings.data.active_preset = new_id
                self.settings.save()
            for g in self.games.games:
                if g.preset_id == EDITOR_PRESET_ID:
                    g.preset_id = new_id
            self.games.save()
            self.state.set("migrated_v2", True)
            log.info("migrated_editor_flags preset=%s", new_id)
        except Exception as e:  # noqa  移行失敗でも起動は継続（次回再試行）
            log.error("migration_failed %s", e)

    def selected_game(self):
        g = self.games.get(self.settings.data.selected_game_id)
        return g or (self.games.games[0] if self.games.games else None)

    def select_game(self, gid: str):
        self.settings.data.selected_game_id = gid
        self.settings.save()

    def active_preset(self):
        return self.presets.get(self.settings.data.active_preset)

    def preset_apply_state(self, pid: str) -> tuple[str, str]:
        """('applied'|'modified'|'outdated'|'none', 適用日時)。書き込み済み≠Robloxでの反映確認済み。"""
        la, p = self.state.get("last_apply"), self.presets.get(pid)
        if not la or not la.get("ok") or la.get("preset") != pid or p is None:
            return "none", ""
        if (p.get("updated_at") or "") > la.get("at", ""):
            return "modified", la["at"]
        inst = self.last_detection.install
        if inst and la.get("version_dir") != str(inst.version_dir):
            return "outdated", la["at"]
        return "applied", la["at"]

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
        return [("", tr("（適用しない）"))] + \
               [(p["id"], tr("{0}［{1}］", p['name'], p['category'])) for p in self.presets.presets]

    def detect_outcome(self, use_network: bool = True) -> Detection:
        try:
            d = Detection(install=self.detector.detect(use_network))
        except RobloxNotFound as e:
            d = Detection(code="NOT_FOUND", message=str(e))
        except RobloxAmbiguous as e:
            d = Detection(code="AMBIGUOUS", message=str(e), candidates=e.candidates)
        except Exception as e:  # noqa  検出中の予期しない例外でも落とさない
            log.exception("detect_error")
            d = Detection(code="ERROR", message=tr("検出中にエラーが発生しました: {0}", e))
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
                 tr("時刻: {0}", datetime.now().isoformat(timespec='seconds')),
                 tr("Roblox検出: {0}", 'OK ' + str(d.install.version_dir) + ' (' + d.install.verified_by + ')' if d.install else d.code + ' ' + d.message),
                 tr("許可リスト: {0}", self.allowlist.state_text()),
                 tr("フラグ数: {0} / プリセット数: {1} / ゲーム数: {2}", len(self.flags.flags), len(self.presets.presets), len(self.games.games)),
                 tr("最後の適用: {0}", self.state.get('last_apply')), "", tr("---- ログ ----"), *MEMORY.lines]
        return anonymize("\n".join(lines))

    def export_diagnostics(self, dest: Path) -> Path:
        dest = Path(dest)
        dest.write_text(self.diagnostics_text(), encoding="utf-8")
        log.info("diagnostics_exported")
        return dest

    def shutdown(self):
        log.info("app_exit")
