"""ゲームライブラリ。Place ID/URLの厳格な検証を含む。"""
from __future__ import annotations
from .i18n import tr, N_
import logging
import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from urllib.parse import urlsplit, urlparse, parse_qs

from .jsonio import read_json, write_json
from .net import http_get_json, NetworkError

log = logging.getLogger("polaris.games")
PLACE_ID_MAX = 2 ** 53
_PATH = re.compile(r"^/(?:[A-Za-z]{2}(?:-[A-Za-z]{2})?/)?games/([0-9]{1,16})(?:/[^/?#]*)?/?$")


class InvalidPlace(ValueError):
    pass


def validate_place_id(v) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not (1 <= v <= PLACE_ID_MAX):
        raise InvalidPlace(tr("Place IDが不正です: {0!r}", v))
    return v


def parse_place_input(text: str) -> int:
    """数字のPlace ID、または https://www.roblox.com/games/<id>/... 形式のURLのみ受け付ける。"""
    s = (text or "").strip()
    if not s:
        raise InvalidPlace(tr("Place IDまたはURLを入力してください"))
    if re.fullmatch(r"[0-9]{1,16}", s):
        return validate_place_id(int(s))
    if re.match(r"(?i)^(www\.)?roblox\.com/", s):
        s = "https://" + s
    try:
        u = urlsplit(s)
    except ValueError:
        raise InvalidPlace(tr("URLを解析できません"))
    if u.scheme.lower() != "https":
        raise InvalidPlace(tr("https のRoblox URLのみ対応しています"))
    if u.netloc.lower() not in ("www.roblox.com", "roblox.com"):
        raise InvalidPlace(tr("roblox.com 以外のURLは対応していません"))
    m = _PATH.match(u.path)
    if not m:
        raise InvalidPlace(tr("対応形式は https://www.roblox.com/games/<PlaceID>/... です"))
    return validate_place_id(int(m.group(1)))


def build_launch_uri(place_id: int) -> str:
    return f"roblox://experiences/start?placeId={validate_place_id(place_id)}"


def uri_place_id(uri: str) -> int | None:
    u = urlparse(uri)
    if u.scheme != "roblox" or u.netloc != "experiences" or u.path != "/start":
        return None
    v = parse_qs(u.query).get("placeId", [])
    return int(v[0]) if len(v) == 1 and v[0].isdigit() else None


def fetch_game_name(place_id: int, timeout: float = 6.0) -> str:
    validate_place_id(place_id)
    uni = http_get_json(f"https://apis.roblox.com/universes/v1/places/{place_id}/universe", timeout)
    uid = uni.get("universeId") if isinstance(uni, dict) else None
    if not isinstance(uid, int):
        raise NetworkError(tr("ゲーム情報が見つかりません（非公開、または存在しないPlace ID）"))
    info = http_get_json(f"https://games.roblox.com/v1/games?universeIds={uid}", timeout)
    data = info.get("data") if isinstance(info, dict) else None
    if not data or not isinstance(data[0].get("name"), str):
        raise NetworkError(tr("ゲーム名を取得できませんでした"))
    return data[0]["name"][:100]


@dataclass
class Game:
    id: str
    name: str
    place_id: int
    favorite: bool = False
    note: str = ""
    preset_id: str = ""
    apply_flags: bool = True
    verify_process: bool = True
    launch_count: int = 0
    last_launched: str = ""
    added_at: str = ""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class GameLibrary:
    def __init__(self, path):
        self.path = path
        self.games: list[Game] = []
        self.load()

    def load(self):
        data = read_json(self.path, {"version": 1, "games": []}, lambda d: isinstance(d, dict))
        self.games = []
        for it in data.get("games", []):
            try:
                g = Game(**{k: it[k] for k in Game.__dataclass_fields__ if k in it})
                validate_place_id(g.place_id)
                self.games.append(g)
            except (TypeError, KeyError, InvalidPlace, AttributeError):
                log.warning("不正なゲーム項目をスキップ")

    def save(self):
        write_json(self.path, {"version": 1, "games": [asdict(g) for g in self.games]})

    def get(self, gid) -> Game | None:
        return next((g for g in self.games if g.id == gid), None)

    def add(self, place_input, name: str = "") -> Game:
        pid = parse_place_input(place_input) if not isinstance(place_input, int) else validate_place_id(place_input)
        if any(g.place_id == pid for g in self.games):
            raise ValueError(tr("Place ID {0} は既に登録されています", pid))
        g = Game(uuid.uuid4().hex, (name or "").strip()[:100] or f"Place {pid}", pid, added_at=now_iso())
        self.games.append(g)
        log.info("game_add place_id=%d", pid)
        self.save()
        return g

    def update(self, gid, **kw):
        g = self.get(gid)
        if g is None:
            raise KeyError(gid)
        if "place_id" in kw:
            kw["place_id"] = validate_place_id(kw["place_id"])
        if "name" in kw:
            kw["name"] = kw["name"].strip()[:100] or f"Place {kw.get('place_id', g.place_id)}"
        for k, v in kw.items():
            setattr(g, k, v)
        self.save()

    def delete(self, gid):
        self.games = [g for g in self.games if g.id != gid]
        self.save()

    def search(self, q: str) -> list[Game]:
        q = q.strip().lower()
        return [g for g in self.games if not q or q in g.name.lower() or q in str(g.place_id)]

    def record_launch(self, gid):
        g = self.get(gid)
        if g:
            g.launch_count += 1
            g.last_launched = now_iso()
            self.save()

    def recent(self, n=8) -> list[Game]:
        return sorted([g for g in self.games if g.last_launched], key=lambda g: g.last_launched, reverse=True)[:n]

    def favorites(self) -> list[Game]:
        return [g for g in self.games if g.favorite]
