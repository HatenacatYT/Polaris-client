"""外部リンクの一元管理。実在するURLが提供されるまで空欄（未設定）とし、架空のURLは使用しない。
変更方法: ここを書き換えるか、データフォルダの links.json（{"youtube": "https://..."}）で上書きする。"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

log = logging.getLogger("polaris.links")

LINKS = {"youtube": "", "terms": "", "privacy": "", "support": "", "website": ""}
AUTHOR = ""  # 製作者名（未設定なら「未設定」と表示）


def _valid(u) -> bool:
    try:
        p = urlsplit(u)
        return p.scheme == "https" and bool(p.netloc)
    except ValueError:
        return False


def get_links(data_dir: Path) -> dict[str, str]:
    out = {k: (v if _valid(v) else "") for k, v in LINKS.items()}
    f = Path(data_dir) / "links.json"
    if f.is_file():
        try:
            for k, v in json.loads(f.read_text("utf-8")).items():
                if k in out and isinstance(v, str) and _valid(v):
                    out[k] = v
        except (OSError, ValueError, AttributeError) as e:
            log.warning("links.json を読み込めません: %s", e)
    return out
