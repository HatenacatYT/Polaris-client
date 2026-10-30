"""安全なHTTP取得（https・roblox.comドメインのみ・タイムアウト・サイズ上限）。"""
from __future__ import annotations
from .i18n import tr, N_
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class NetworkError(Exception):
    pass


def http_get(url: str, timeout: float = 6.0, max_bytes: int = 3_000_000) -> bytes:
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not (host == "roblox.com" or host.endswith(".roblox.com")):
        raise NetworkError(tr("許可されていないURLです: {0}", url))
    req = urllib.request.Request(url, headers={"User-Agent": "Polaris/1.0", "Accept": "application/json,text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(max_bytes + 1)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise NetworkError(tr("通信に失敗しました: {0}", e)) from e
    if len(data) > max_bytes:
        raise NetworkError(tr("応答が大きすぎます"))
    return data


def http_get_json(url: str, timeout: float = 6.0):
    try:
        return json.loads(http_get(url, timeout).decode("utf-8", "replace"))
    except ValueError as e:
        raise NetworkError(tr("JSON解析に失敗しました: {0}", e)) from e
