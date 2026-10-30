"""FastFlagのモデル・検証・差分・プリセット。アプリ独自データとRoblox出力は分離する。"""
from __future__ import annotations
from .i18n import tr, N_
import json
import logging
import math
import re
import uuid
from dataclasses import dataclass, asdict
from typing import Any

from .jsonio import read_json, write_json

log = logging.getLogger("polaris.flags")
FLAG_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,127}$")
CATEGORIES = ["レンダリング", "グラフィックス", "UI", "パフォーマンス", "ネットワーク", "その他"]
EDITOR_PRESET_ID = "__editor__"


def value_type(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    return "invalid"


def validate_flag(name: Any, value: Any) -> list[str]:
    errs = []
    if not isinstance(name, str) or not FLAG_NAME_RE.match(name):
        errs.append(tr("不正なフラグ名: {0!r}", name))
    t = value_type(value)
    if t == "invalid":
        errs.append(tr("{0}: 未対応の値の型です（真偽値・数値・文字列のみ）", name))
    elif t == "float" and not math.isfinite(value):
        errs.append(tr("{0}: 数値が不正です", name))
    elif t == "string" and len(value) > 1024:
        errs.append(tr("{0}: 文字列が長すぎます", name))
    return errs


def validate_flags(d: dict) -> list[str]:
    errs: list[str] = []
    for k, v in d.items():
        errs += validate_flag(k, v)
    return errs


def parse_value_text(text: str) -> Any:
    """入力テキスト→JSON値。JSONとして解釈できなければ文字列として扱う（例: True は文字列）。"""
    s = text.strip()
    if not s:
        raise ValueError(tr("値が空です"))
    try:
        v = json.loads(s, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(tr("使用できない定数"))))
    except ValueError:
        return s
    if isinstance(v, (bool, int, float, str)):
        return v
    raise ValueError(tr("値には真偽値・数値・文字列のみ使用できます"))


def loads_checked(text: str) -> tuple[dict | None, list[str], list[str]]:
    """JSON文字列を検証。戻り値: (dict|None, 重複キー, エラー)。"""
    dups: list[str] = []

    def hook(pairs):
        seen: dict = {}
        for k, v in pairs:
            if k in seen:
                dups.append(k)
            seen[k] = v
        return seen

    def bad(c):
        raise ValueError(tr("使用できない定数: {0}", c))

    try:
        data = json.loads(text, object_pairs_hook=hook, parse_constant=bad)
    except ValueError as e:
        return None, sorted(set(dups)), [tr("JSON構文エラー: {0}", e)]
    if not isinstance(data, dict):
        return None, [], [tr("最上位は {...} 形式のオブジェクトである必要があります")]
    return data, sorted(set(dups)), validate_flags(data)


def to_roblox_payload(flags: dict[str, Any], fmt: str = "string") -> dict[str, Any]:
    """Roblox用ClientAppSettings.jsonの内容を生成（アプリ内メタデータは含めない）。
    fmt='string': Bloxstrap等と同様に値を文字列化 / 'native': JSON型のまま。"""
    if fmt == "native":
        return dict(flags)
    out: dict[str, Any] = {}
    for k, v in flags.items():
        out[k] = ("True" if v else "False") if isinstance(v, bool) else (v if isinstance(v, str) else str(v))
    return out


@dataclass
class FlagDiff:
    added: dict
    changed: dict
    removed: dict
    unchanged: int

    @property
    def empty(self) -> bool:
        return not (self.added or self.changed or self.removed)

    def to_text(self) -> str:
        lines = []
        for k, v in self.added.items():
            lines.append(f"+ {k} = {v!r}")
        for k, (o, n) in self.changed.items():
            lines.append(f"~ {k}: {o!r} → {n!r}")
        for k, v in self.removed.items():
            lines.append(tr("- {0} (現在の値: {1!r})", k, v))
        return "\n".join(lines) or tr("（変更なし）")


def diff_payload(old: dict, new: dict) -> FlagDiff:
    added = {k: v for k, v in new.items() if k not in old}
    removed = {k: v for k, v in old.items() if k not in new}
    changed = {k: (old[k], new[k]) for k in new if k in old and old[k] != new[k]}
    return FlagDiff(added, changed, removed, len(new) - len(added) - len(changed))


@dataclass
class Flag:
    name: str
    value: Any
    enabled: bool = True
    category: str = "その他"
    favorite: bool = False
    note: str = ""


class FlagStore:
    def __init__(self, path):
        self.path = path
        self.flags: dict[str, Flag] = {}
        self.load()

    def load(self):
        data = read_json(self.path, {"version": 1, "flags": []}, lambda d: isinstance(d, dict))
        self.flags = {}
        for it in data.get("flags", []):
            try:
                f = Flag(**{k: it[k] for k in Flag.__dataclass_fields__ if k in it})
                if not validate_flag(f.name, f.value) and f.name not in self.flags:
                    if f.category not in CATEGORIES:
                        f.category = "その他"
                    self.flags[f.name] = f
                else:
                    log.warning("不正/重複フラグをスキップ: %r", it.get("name"))
            except (TypeError, KeyError, AttributeError):
                log.warning("読み込めないフラグ項目をスキップ")

    def save(self):
        write_json(self.path, {"version": 1, "flags": [asdict(f) for f in self.flags.values()]})

    def add(self, name, value, category="その他", note="", enabled=True, save=True) -> Flag:
        name = name.strip()
        errs = validate_flag(name, value)
        if errs:
            raise ValueError("; ".join(errs))
        if name in self.flags:
            raise ValueError(tr("{0} は既に存在します", name))
        f = self.flags[name] = Flag(name, value, enabled, category if category in CATEGORIES else "その他", False, note)
        log.info("flag_add name=%s", name)
        if save:
            self.save()
        return f

    def update_value(self, name, value):
        errs = validate_flag(name, value)
        if errs:
            raise ValueError("; ".join(errs))
        self.flags[name].value = value
        log.info("flag_edit name=%s", name)
        self.save()

    def rename(self, old, new):
        new = new.strip()
        if new == old:
            return
        if new in self.flags:
            raise ValueError(tr("{0} は既に存在します", new))
        errs = validate_flag(new, self.flags[old].value)
        if errs:
            raise ValueError("; ".join(errs))
        self.flags = {(new if k == old else k): (self._ren(v, new) if k == old else v) for k, v in self.flags.items()}
        self.save()

    @staticmethod
    def _ren(f: Flag, n: str) -> Flag:
        f.name = n
        return f

    def delete(self, names):
        for n in names:
            self.flags.pop(n, None)
        log.info("flag_delete count=%d", len(list(names)))
        self.save()

    def set_attr(self, names, **kw):
        for n in names:
            if n in self.flags:
                for k, v in kw.items():
                    if k == "category" and v not in CATEGORIES:
                        v = "その他"
                    setattr(self.flags[n], k, v)
        self.save()

    def import_flags(self, data: dict, overwrite: bool) -> tuple[int, int]:
        if overwrite:
            self.flags = {}
        added = updated = 0
        for k, v in data.items():
            if k in self.flags:
                self.flags[k].value = v
                updated += 1
            else:
                self.flags[k] = Flag(k, v)
                added += 1
        log.info("flag_import added=%d updated=%d overwrite=%s", added, updated, overwrite)
        self.save()
        return added, updated

    def enabled_dict(self) -> dict[str, Any]:
        return {n: f.value for n, f in self.flags.items() if f.enabled}


class DuplicateName(ValueError):
    pass


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def check_preset_name(name: str) -> str:
    """不正な名前なら理由を返す（空文字=問題なし）。"""
    n = (name or "").strip()
    if not n:
        return tr("名前を入力してください")
    if len(n) > 60:
        return tr("名前は60文字以内にしてください")
    if any(ord(c) < 32 for c in n):
        return tr("名前に使用できない文字が含まれています")
    return ""


class PresetStore:
    def __init__(self, path):
        self.path = path
        self.presets: list[dict] = []
        self.load()

    def load(self):
        data = read_json(self.path, {"version": 1, "presets": []}, lambda d: isinstance(d, dict))
        self.presets = []
        for p in data.get("presets", []):
            if isinstance(p, dict) and isinstance(p.get("flags"), dict) and isinstance(p.get("name"), str):
                p.setdefault("id", uuid.uuid4().hex)
                p["category"] = p.get("category") if p.get("category") in CATEGORIES else "その他"
                p["description"] = p.get("description") if isinstance(p.get("description"), str) else ""
                p.setdefault("created_at", ""); p.setdefault("updated_at", p.get("created_at", ""))
                self.presets.append(p)

    def save(self):
        write_json(self.path, {"version": 1, "presets": self.presets})

    def get(self, pid):
        return next((p for p in self.presets if p["id"] == pid), None)

    def name_exists(self, name: str, exclude: str | None = None) -> bool:
        n = name.strip().casefold()
        return any(p["name"].strip().casefold() == n and p["id"] != exclude for p in self.presets)

    def unique_name(self, base: str) -> str:
        base, i, cand = base.strip(), 2, base.strip()
        while self.name_exists(cand):
            cand, i = f"{base} ({i})", i + 1
        return cand

    def create(self, name, category="その他", flags=None, description="") -> dict:
        name = name.strip()
        bad = check_preset_name(name)
        if bad:
            raise ValueError(bad)
        if self.name_exists(name):
            raise DuplicateName(tr("同名のプリセットが既に存在します: {0}", name))
        errs = validate_flags(flags or {})
        if errs:
            raise ValueError("; ".join(errs))
        now = _now()
        p = {"id": uuid.uuid4().hex, "name": name, "description": description.strip()[:200],
             "category": category if category in CATEGORIES else "その他", "flags": dict(flags or {}),
             "created_at": now, "updated_at": now}
        self.presets.append(p)
        log.info("preset_create name=%s", name)
        self.save()
        return p

    def update(self, pid, **kw):
        p = self.get(pid)
        if p is None:
            raise KeyError(pid)
        if "flags" in kw:
            errs = validate_flags(kw["flags"])
            if errs:
                raise ValueError("; ".join(errs))
        if "name" in kw:
            kw["name"] = kw["name"].strip()
            bad = check_preset_name(kw["name"])
            if bad:
                raise ValueError(bad)
            if self.name_exists(kw["name"], exclude=pid):
                raise DuplicateName(tr("同名のプリセットが既に存在します: {0}", kw['name']))
        if "category" in kw and kw["category"] not in CATEGORIES:
            kw["category"] = "その他"
        p.update(kw)
        p["updated_at"] = _now()
        self.save()

    def rename(self, pid, name):
        self.update(pid, name=name)

    def duplicate(self, pid) -> dict:
        p = self.get(pid)
        if p is None:
            raise KeyError(pid)
        return self.create(self.unique_name(p["name"] + " (copy)"), p["category"], p["flags"], p.get("description", ""))

    def delete(self, pid):
        self.presets = [p for p in self.presets if p["id"] != pid]
        self.save()
