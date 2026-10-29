"""アプリのデータ保存先（AppData配下）。"""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "Polaris"


@dataclass
class AppPaths:
    root: Path

    def __post_init__(self):
        self.root = Path(self.root)
        for d in (self.root, self.logs, self.default_backups):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def default(cls) -> "AppPaths":
        base = os.environ.get("APPDATA")
        return cls(Path(base) / APP_DIR_NAME if base else Path.home() / ".polaris")

    logs = property(lambda s: s.root / "logs")
    default_backups = property(lambda s: s.root / "backups")
    settings_file = property(lambda s: s.root / "app_settings.json")
    games_file = property(lambda s: s.root / "games.json")
    flags_file = property(lambda s: s.root / "fastflags.json")
    presets_file = property(lambda s: s.root / "presets.json")
    allowlist_file = property(lambda s: s.root / "allowlist.json")
    state_file = property(lambda s: s.root / "state.json")
