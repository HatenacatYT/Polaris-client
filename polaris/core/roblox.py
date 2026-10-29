"""Roblox Player のインストール検出。バージョンフォルダ名は固定せず、実体を検証して判断する。"""
from __future__ import annotations
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .net import http_get_json, NetworkError

log = logging.getLogger("polaris.roblox")
PLAYER_EXE = "RobloxPlayerBeta.exe"
LAUNCHER_EXE = "RobloxPlayerLauncher.exe"
OFFICIAL_VERSION_URL = "https://clientsettingscdn.roblox.com/v2/client-version/WindowsPlayer"


class RobloxNotFound(Exception):
    pass


class RobloxAmbiguous(Exception):
    def __init__(self, msg, candidates):
        super().__init__(msg)
        self.candidates = list(candidates)


@dataclass
class RobloxInstall:
    version_dir: Path
    version_name: str
    player_exe: Path
    launcher_exe: Path | None
    verified_by: str
    detected_at: str
    candidate_count: int = 1


def default_roots() -> list[Path]:
    roots = []
    for var in ("LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"):
        v = os.environ.get(var)
        if v:
            roots.append(Path(v) / "Roblox" / "Versions")
    return roots


def registry_hint() -> Path | None:
    """roblox-player プロトコル登録から、実行ファイルのあるフォルダを得る（Windowsのみ）。"""
    if os.name != "nt":
        return None
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"Software\Classes\roblox-player\shell\open\command") as k:
                    cmd = winreg.QueryValueEx(k, "")[0]
            except OSError:
                continue
            m = re.match(r'\s*"([^"]+)"', cmd) or re.match(r"\s*(\S+)", cmd)
            if m:
                return Path(m.group(1)).parent
    except Exception as e:  # noqa
        log.warning("レジストリ参照失敗: %s", e)
    return None


def fetch_official_version(timeout: float = 5.0) -> str | None:
    try:
        d = http_get_json(OFFICIAL_VERSION_URL, timeout)
        v = d.get("clientVersionUpload") if isinstance(d, dict) else None
        return v if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", v) else None
    except NetworkError as e:
        log.info("公式バージョン取得不可(オフライン可): %s", e)
        return None


def client_settings_path(inst: RobloxInstall) -> Path:
    return inst.version_dir / "ClientSettings" / "ClientAppSettings.json"


class Detector:
    def __init__(self, roots=None, registry_fn=registry_hint, official_fn=fetch_official_version, pinned_fn=lambda: ""):
        self.roots = roots if roots is not None else default_roots()
        self.registry_fn, self.official_fn, self.pinned_fn = registry_fn, official_fn, pinned_fn

    def candidates(self) -> list[Path]:
        out: list[Path] = []
        for root in self.roots:
            try:
                if not Path(root).is_dir():
                    continue
                for d in sorted(Path(root).iterdir()):
                    if d.is_dir() and (d / PLAYER_EXE).is_file() and d not in out:
                        out.append(d)
            except OSError as e:
                log.warning("走査失敗 %s: %s", root, e)
        return out

    def _make(self, d: Path, how: str, n: int) -> RobloxInstall:
        lx = d / LAUNCHER_EXE
        inst = RobloxInstall(d, d.name, d / PLAYER_EXE, lx if lx.is_file() else None, how,
                             datetime.now().isoformat(timespec="seconds"), n)
        log.info("roblox_detected path=%s verified_by=%s candidates=%d", d, how, n)
        return inst

    def detect(self, use_network: bool = True) -> RobloxInstall:
        cands = self.candidates()
        if not cands:
            log.warning("roblox_not_found roots=%s", [str(r) for r in self.roots])
            raise RobloxNotFound("Roblox Player が見つかりません。Robloxをインストールして一度起動してください。")
        if len(cands) == 1:
            return self._make(cands[0], "唯一の有効な環境", 1)
        # 複数: 公式の最新バージョン名 → プロトコル登録 → ユーザー固定 の順。更新日時は根拠にしない。
        official = self.official_fn() if use_network else None
        if official:
            for d in cands:
                if d.name == official:
                    return self._make(d, "公式の最新バージョンと一致", len(cands))
        hint = self.registry_fn()
        if hint:
            for d in cands:
                if d == hint or d.resolve() == Path(hint).resolve():
                    return self._make(d, "プロトコル登録(レジストリ)と一致", len(cands))
        pin = self.pinned_fn()
        if pin:
            for d in cands:
                if str(d) == pin:
                    return self._make(d, "ユーザーが選択した環境", len(cands))
        log.warning("roblox_ambiguous candidates=%s", [str(c) for c in cands])
        raise RobloxAmbiguous("有効なRobloxの環境が複数あり、どれが現在使用中か判断できません。使用する環境を選択してください。", cands)


def roblox_process_running() -> bool:
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {PLAYER_EXE}", "/NH", "/FO", "CSV"],
                           capture_output=True, text=True, errors="replace", timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return PLAYER_EXE.lower() in r.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False
