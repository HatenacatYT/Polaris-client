"""公式FastFlag許可リストの取得・保持。古い情報を最新として扱わない。"""
from __future__ import annotations
import html
import logging
import re
from datetime import datetime, timedelta

from .jsonio import read_json, write_json
from .net import http_get_json, NetworkError

log = logging.getLogger("polaris.allowlist")
SOURCE_URL = "https://devforum.roblox.com/t/allowlist-for-local-client-configuration-via-fast-flags/3966569"
JSON_URL = SOURCE_URL + ".json"
FRESH_HOURS = 24
_NAME = re.compile(r"\b(?:FFlag|DFFlag|SFFlag|FInt|DFInt|SFInt|FString|DFString|SFString|FLog|DFLog)[A-Za-z0-9_]+")


class AllowlistError(Exception):
    pass


def extract_flag_names(text: str) -> set[str]:
    plain = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return set(_NAME.findall(plain))


class AllowlistStore:
    def __init__(self, path, now=datetime.now):
        self.path, self.now = path, now
        d = read_json(path, {}, lambda x: isinstance(x, dict))
        self.names: set[str] = set(n for n in d.get("names", []) if isinstance(n, str))
        self.fetched_at: str = d.get("fetched_at", "") if self.names else ""
        self.source: str = d.get("source", "")
        self.method: str = d.get("method", "")

    @property
    def fresh(self) -> bool:
        if not self.names or not self.fetched_at:
            return False
        try:
            return self.now() - datetime.fromisoformat(self.fetched_at) < timedelta(hours=FRESH_HOURS)
        except ValueError:
            return False

    def state_text(self) -> str:
        if not self.names:
            return "未取得（公式リストを確認できていません）"
        s = f"{len(self.names)}件 / 確認日時 {self.fetched_at} / 情報源 {self.source}"
        return s if self.fresh else s + " ／ ⚠ 古い情報の可能性（再取得してください）"

    def status(self, name: str) -> str:
        """allowed: 公式掲載(最新) / not_listed: 最新リストに無い / unverified: 確認不能(未取得・期限切れ)"""
        if not self.fresh:
            return "unverified"
        return "allowed" if name in self.names else "not_listed"

    def _store(self, names: set[str], source: str, method: str):
        self.names, self.source, self.method = names, source, method
        self.fetched_at = self.now().isoformat(timespec="seconds")
        write_json(self.path, {"names": sorted(names), "fetched_at": self.fetched_at, "source": source, "method": method})
        log.info("allowlist_updated count=%d method=%s", len(names), method)

    def refresh_online(self, fetch=http_get_json) -> int:
        try:
            data = fetch(JSON_URL)
            posts = data["post_stream"]["posts"]
            cooked = posts[0]["cooked"]
        except (NetworkError, KeyError, IndexError, TypeError) as e:
            log.warning("allowlist取得失敗: %s", e)
            raise AllowlistError(f"公式リストの取得に失敗しました: {e}") from e
        names = extract_flag_names(cooked)  # 1つ目（公式）投稿のみ対象。コメントは対象外。
        if not names:
            raise AllowlistError("公式投稿からフラグ名を抽出できませんでした（投稿の形式が変わった可能性）")
        self._store(names, SOURCE_URL + "（自動抽出）", "online")
        return len(names)

    def import_text(self, text: str, label: str) -> int:
        names = extract_flag_names(text)
        if not names:
            raise AllowlistError("ファイル内にフラグ名が見つかりません")
        self._store(names, f"ユーザー提供ファイル: {label}", "file")
        return len(names)
