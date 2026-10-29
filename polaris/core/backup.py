"""バックアップ/復元。保存先・保存数・保存期間は設定可能。"""
from __future__ import annotations
import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from .jsonio import read_json, write_json, StorageError

log = logging.getLogger("polaris.backup")
ALLOWED_NAMES = {"ClientAppSettings.json", "fastflags.json", "presets.json", "games.json", "app_settings.json"}


class RestoreError(Exception):
    pass


@dataclass
class BackupEntry:
    id: str
    created_at: str
    kind: str
    label: str
    dir: Path
    files: list[dict]


class BackupManager:
    def __init__(self, get_dir: Callable[[], Path]):
        self.get_dir = get_dir

    def create(self, kind: str, label: str, files: list[Path]) -> BackupEntry:
        files = [Path(f) for f in files if Path(f).is_file()]
        if not files:
            raise StorageError("バックアップ対象のファイルがありません")
        bid = f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}-{kind}"
        d = Path(self.get_dir()) / bid
        try:
            d.mkdir(parents=True, exist_ok=False)
            meta_files = []
            for i, f in enumerate(files):
                stored = f"{i}_{f.name}"
                shutil.copy2(f, d / stored)
                meta_files.append({"stored": stored, "name": f.name, "source": str(f)})
            meta = {"id": bid, "created_at": datetime.now().isoformat(timespec="seconds"),
                    "kind": kind, "label": label, "files": meta_files}
            write_json(d / "meta.json", meta, keep_bak=False)
        except OSError as e:
            shutil.rmtree(d, ignore_errors=True)
            raise StorageError(f"バックアップを作成できません（権限・容量を確認）: {e}") from e
        log.info("backup_created id=%s kind=%s files=%s", bid, kind, [m["source"] for m in meta_files])
        return BackupEntry(bid, meta["created_at"], kind, label, d, meta_files)

    def list(self) -> list[BackupEntry]:
        base = Path(self.get_dir())
        out = []
        if not base.is_dir():
            return out
        for d in base.iterdir():
            mp = d / "meta.json"
            if not mp.is_file():
                continue
            try:
                m = json.loads(mp.read_text("utf-8"))
                out.append(BackupEntry(m["id"], m["created_at"], m["kind"], m.get("label", ""), d, m["files"]))
            except (OSError, ValueError, KeyError, TypeError):
                log.warning("壊れたバックアップ情報をスキップ: %s", d)
        return sorted(out, key=lambda e: e.created_at, reverse=True)

    def get(self, bid: str) -> BackupEntry | None:
        return next((e for e in self.list() if e.id == bid), None)

    @staticmethod
    def _check_target(name: str, target: Path):
        if name not in ALLOWED_NAMES or target.name != name:
            raise RestoreError(f"復元先として許可されていないファイルです: {target.name}")
        if name == "ClientAppSettings.json" and target.parent.name != "ClientSettings":
            raise RestoreError("Roblox設定の復元先が ClientSettings フォルダではありません")

    def restore(self, bid: str) -> list[Path]:
        e = self.get(bid)
        if e is None:
            raise RestoreError("バックアップが見つかりません")
        plan = []
        for m in e.files:
            src, target = e.dir / m["stored"], Path(m["source"])
            self._check_target(m["name"], target)
            try:
                json.loads(src.read_text("utf-8"))
            except (OSError, ValueError) as ex:
                raise RestoreError(f"バックアップ内の {m['name']} が壊れています: {ex}") from ex
            if not target.parent.exists() and m["name"] != "ClientAppSettings.json":
                target.parent.mkdir(parents=True, exist_ok=True)
            if m["name"] == "ClientAppSettings.json" and not target.parent.parent.exists():
                raise RestoreError(f"復元先のRobloxフォルダが存在しません（Roblox更新で場所が変わった可能性）: {target.parent.parent}\n"
                                   "Roblox環境を再検出し、FastFlag適用で新しい環境へ反映してください。")
            plan.append((src, target))
        done = []
        for src, target in plan:
            tmp = None
            try:
                if target.exists():
                    self.create("pre-restore", f"復元前の自動退避 ({e.id})", [target])
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
                os.close(fd)
                tmp = Path(name)
                shutil.copyfile(src, tmp)
                os.replace(tmp, target)
                tmp = None
                done.append(target)
            except PermissionError as ex:
                raise RestoreError(f"書き込み権限がないか、他のアプリが使用中です: {target}\n"
                                   "Robloxを終了し、ファイルが読み取り専用でないか確認してから再試行してください。") from ex
            except (OSError, StorageError) as ex:
                raise RestoreError(f"復元に失敗しました: {ex}\n復元前の状態は『pre-restore』バックアップから戻せます。") from ex
            finally:
                if tmp is not None:
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
        log.info("backup_restored id=%s targets=%s", bid, [str(t) for t in done])
        return done

    def delete(self, bid: str):
        e = self.get(bid)
        if e:
            shutil.rmtree(e.dir, ignore_errors=True)
            log.info("backup_deleted id=%s", bid)

    def prune(self, max_count: int, max_days: int) -> int:
        removed = 0
        entries = self.list()
        for i, e in enumerate(entries):
            too_many = max_count > 0 and i >= max_count
            too_old = False
            if max_days > 0:
                try:
                    too_old = datetime.now() - datetime.fromisoformat(e.created_at) > timedelta(days=max_days)
                except ValueError:
                    pass
            if too_many or too_old:
                shutil.rmtree(e.dir, ignore_errors=True)
                removed += 1
        if removed:
            log.info("backup_pruned removed=%d", removed)
        return removed
