"""翻訳の網羅性: コード内の tr()/N_() の全キーに英訳があり、プレースホルダが一致すること。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from collect_keys import collect  # noqa: E402

from polaris.core import i18n
from polaris.core.i18n import tr, set_language
from polaris.core.i18n_en import EN

CJK = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")
JP = re.compile(r"[\u3040-\u309f\u30a0-\u30fa\u30fc-\u30ff\u3400-\u9fff]")   # ひらがな・カタカナ・漢字（「・」「＋」等の記号は除く）
PH = lambda s: sorted(re.findall(r"\{\d+(?:![rsa])?(?::[^}]*)?\}", s))


def test_every_key_has_english():
    root = Path(__file__).resolve().parent.parent
    missing = [k for k in collect(str(root / "polaris")) if CJK.search(k) and k not in EN]
    assert not missing, f"未翻訳 {len(missing)}件: {missing[:5]}"


def test_no_stale_or_broken_translations():
    keys = set(collect(str(Path(__file__).resolve().parent.parent / "polaris")))
    assert not [k for k in EN if k not in keys], "コードに存在しない翻訳キー"
    assert all(v.strip() and not JP.search(v) for v in EN.values()), "英訳に日本語が残っている/空"
    assert not [k for k, v in EN.items() if PH(k) != PH(v)], "プレースホルダ不一致"


def test_language_switch_and_fallback():
    try:
        set_language("en")
        assert tr("キャンセル") == "Cancel"
        assert tr("{0}件を読み込みました（ユーザー提供ファイル）", 3) == "Loaded 3 items (user-provided file)"
        assert tr("未登録の日本語キー") == "未登録の日本語キー"        # 未翻訳は日本語へフォールバック
        set_language("xx")
        assert i18n.language() == "ja" and tr("キャンセル") == "キャンセル"
    finally:
        set_language("ja")
