"""アプリ設定(app_settings.json)と状態(state.json)。"""
from __future__ import annotations
from dataclasses import dataclass, asdict, fields
from typing import Any

from .jsonio import read_json, write_json


@dataclass
class AppSettings:
    animations: bool = True
    sidebar_collapsed: bool = False
    confirm_before_apply: bool = True
    value_format: str = "string"          # "string" | "native"
    default_launch_mode: str = "apply_and_play"  # | "play_only"
    auto_check_allowlist: bool = True
    backup_dir: str = ""
    backup_auto_prune: bool = False
    backup_max_count: int = 50
    backup_max_days: int = 0              # 0=無制限
    pinned_version_dir: str = ""
    active_preset: str = ""               # "" | EDITOR_PRESET_ID | preset id
    accent_color: str = "#7c5cff"
    home_background: str = ""


class SettingsStore:
    def __init__(self, path):
        self.path = path
        self.data = AppSettings()
        self.load()

    def load(self):
        raw = read_json(self.path, {}, lambda d: isinstance(d, dict))
        s = AppSettings()
        for f in fields(AppSettings):
            if f.name in raw and isinstance(raw[f.name], type(getattr(s, f.name))):
                setattr(s, f.name, raw[f.name])
        if s.value_format not in ("string", "native"):
            s.value_format = "string"
        s.backup_max_count = max(1, min(10000, s.backup_max_count))
        s.backup_max_days = max(0, min(36500, s.backup_max_days))
        self.data = s

    def save(self):
        write_json(self.path, asdict(self.data))


class StateStore:
    def __init__(self, path):
        self.path = path
        self.d: dict[str, Any] = read_json(path, {}, lambda d: isinstance(d, dict))

    def get(self, k, default=None):
        return self.d.get(k, default)

    def set(self, k, v):
        self.d[k] = v
        write_json(self.path, self.d)
