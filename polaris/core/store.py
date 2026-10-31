"""アプリ設定(app_settings.json)と状態(state.json)。"""
from __future__ import annotations
from dataclasses import dataclass, asdict, fields
from typing import Any

import re

from .i18n import LANGUAGES
from .jsonio import read_json, write_json

ACCENTS = ("cyan", "purple", "red", "green", "navy", "custom")


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
    active_preset: str = ""               # "" | preset id（使用中のプリセット）
    language: str = "ja"
    accent: str = "cyan"
    custom_color: str = "#27a9ff"
    bg_mode: str = "animated"             # "animated" | "video"
    bg_video_path: str = ""               # モードを切り替えても保持する
    bg_overlay: int = 30                  # 動画の上の半透明オーバーレイ(%)
    bg_loop: bool = True                  # 動画のループ再生
    bg_particles: int = 60
    bg_speed: int = 50
    selected_game_id: str = ""
    custom_sky_name: str = ""
    custom_sky_source: str = ""
    custom_sky_source_mode: str = ""
    custom_sky_files: dict = None
    custom_sky_face_targets: dict = None
    custom_sky_applied: bool = False
    custom_sky_backup_id: str = ""
    custom_sky_restore_backup_id: str = ""
    custom_sky_applied_at: str = ""
    custom_sky_applied_version_dir: str = ""
    custom_sky_applied_targets: dict = None
    win_w: int = 1200
    win_h: int = 780

    def __post_init__(self):
        # Avoid shared mutable defaults while retaining compatibility with old
        # settings files, which simply omit these new v1.0.2 fields.
        if self.custom_sky_files is None:
            self.custom_sky_files = {}
        if self.custom_sky_face_targets is None:
            self.custom_sky_face_targets = {}
        if self.custom_sky_applied_targets is None:
            self.custom_sky_applied_targets = {}


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
        if s.language not in LANGUAGES: s.language = "ja"
        if s.accent == "white": s.accent = "navy"      # 旧バージョンの設定を引き継ぐ
        if s.accent not in ACCENTS: s.accent = "cyan"
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", s.custom_color): s.custom_color = "#27a9ff"
        if s.bg_mode not in ("animated", "video"): s.bg_mode = "animated"
        if not isinstance(s.custom_sky_files, dict): s.custom_sky_files = {}
        if not isinstance(s.custom_sky_face_targets, dict): s.custom_sky_face_targets = {}
        if not isinstance(s.custom_sky_applied_targets, dict): s.custom_sky_applied_targets = {}
        s.custom_sky_files = {str(k): str(v) for k, v in s.custom_sky_files.items()
                              if isinstance(k, str) and isinstance(v, str)}
        s.custom_sky_face_targets = {str(k): str(v) for k, v in s.custom_sky_face_targets.items()
                                     if isinstance(k, str) and isinstance(v, str)}
        s.custom_sky_applied_targets = {str(k): str(v) for k, v in s.custom_sky_applied_targets.items()
                                        if isinstance(k, str) and isinstance(v, str)}
        s.bg_overlay = max(0, min(90, s.bg_overlay)); s.bg_particles = max(10, min(150, s.bg_particles))
        s.bg_speed = max(10, min(200, s.bg_speed))
        s.win_w = max(900, min(6000, s.win_w)); s.win_h = max(600, min(4000, s.win_h))
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
