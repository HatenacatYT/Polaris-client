"""翻訳管理。キーは日本語原文（既定言語）。未翻訳のキーは日本語へ安全にフォールバックする。
英語の訳文は i18n_en.py に一元管理する（コード内に散在させない）。"""
from __future__ import annotations

LANGUAGES = {"ja": "日本語", "en": "English"}
_lang = "ja"


def N_(s: str) -> str:
    """翻訳対象のマーカー（モジュール定数用）。表示時に tr() を通す。"""
    return s


def set_language(code: str) -> str:
    global _lang
    _lang = code if code in LANGUAGES else "ja"
    return _lang


def language() -> str:
    return _lang


def _table(lang: str) -> dict:
    if lang == "en":
        from .i18n_en import EN
        return EN
    return {}


def tr(key: str, *args, **kw) -> str:
    text = _table(_lang).get(key, key) if _lang != "ja" else key
    if args or kw:
        try:
            return text.format(*args, **kw)
        except (IndexError, KeyError, ValueError):
            try:
                return key.format(*args, **kw)
            except (IndexError, KeyError, ValueError):
                return text
    return text
