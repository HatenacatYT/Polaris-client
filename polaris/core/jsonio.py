"""破損・途中終了に強いJSON入出力（一時ファイル→検証→置換、.bakから復旧）。"""
from __future__ import annotations
import copy
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("polaris.io")
RECOVERY_NOTES: list[str] = []  # UIが起動後に表示する復旧メモ


class StorageError(Exception):
    pass


def _reject_const(c):
    raise ValueError(f"使用できない定数: {c}")


def _load(p: Path) -> Any:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f, parse_constant=_reject_const)


def read_json(path, default: Any, check: Callable[[Any], bool] | None = None) -> Any:
    path = Path(path)
    bak = path.with_name(path.name + ".bak")
    for cand, is_bak in ((path, False), (bak, True)):
        if not cand.exists():
            continue
        try:
            data = _load(cand)
            if check and not check(data):
                raise ValueError("想定外のデータ構造")
            if is_bak:
                msg = f"{path.name} が破損していたため、直前のバックアップ(.bak)から復旧しました。"
                RECOVERY_NOTES.append(msg)
                log.warning(msg)
            return data
        except (OSError, ValueError) as e:
            log.error("JSON読み込み失敗 %s: %s", cand, e)
            if not is_bak:
                try:
                    q = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
                    os.replace(path, q)
                    RECOVERY_NOTES.append(f"{path.name} が破損していたため {q.name} に退避しました。")
                except OSError:
                    pass
    return default() if callable(default) else copy.deepcopy(default)


def write_json(path, data: Any, *, indent: int | None = 2, keep_bak: bool = True) -> None:
    path = Path(path)
    tmp: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=indent, allow_nan=False)
        fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        tmp = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if json.loads(tmp.read_text("utf-8")) != json.loads(text):
            raise ValueError("書き込み後の検証に失敗")
        if keep_bak and path.exists():
            try:
                shutil.copy2(path, path.with_name(path.name + ".bak"))
            except OSError as e:
                log.warning(".bak作成失敗: %s", e)
        os.replace(tmp, path)
        tmp = None
    except PermissionError as e:
        raise StorageError(f"書き込み権限がない、または他のアプリが使用中です: {path}") from e
    except OSError as e:
        raise StorageError(f"書き込みに失敗しました（ディスク容量不足の可能性）: {path} ({e})") from e
    except (ValueError, TypeError) as e:
        raise StorageError(f"JSONの書き込みに失敗しました: {e}") from e
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
