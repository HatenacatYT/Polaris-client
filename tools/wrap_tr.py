"""開発用: 日本語の文字列リテラルを tr() で包む（一度だけ実行）。f-stringは tr("{0}...", expr) へ変換する。
使い方: python tools/wrap_tr.py <files...>   （冪等。既に tr()/N_() で包まれたものは対象外）"""
import ast, re, sys, json

CJK = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")
SKIP = {"その他", "レンダリング", "グラフィックス", "UI", "パフォーマンス", "ネットワーク"}
report = []


def has_cjk_const(n):
    return isinstance(n, ast.Constant) and isinstance(n.value, str) and CJK.search(n.value)


def process(path):
    src = open(path, "rb").read(); text = src.decode("utf-8")
    offs = [0]
    for l in src.split(b"\n"):
        offs.append(offs[-1] + len(l) + 1)
    pos = lambda ln, col: offs[ln - 1] + col
    tree = ast.parse(text)
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            c._p = n

    def ancestors(n):
        while hasattr(n, "_p"):
            n = n._p; yield n

    def in_func(n):
        prev = n
        for a in ancestors(n):
            if isinstance(a, ast.arguments):
                return False
            if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                return True
            prev = a
        return False

    def skip_ctx(n):
        p = n._p
        if isinstance(p, ast.Call):
            f = p.func
            if isinstance(f, ast.Name) and f.id in ("tr", "N_"): return True
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in ("log", "logger", "logging"): return True
        if isinstance(p, ast.Expr) or isinstance(p, ast.Compare) or isinstance(p, ast.Subscript): return True
        if isinstance(p, ast.Dict) and n in p.keys: return True
        return False

    edits = []
    def seg(n): return src[pos(n.lineno, n.col_offset):pos(n.end_lineno, n.end_col_offset)]

    def visit(n, in_joined=False):
        if isinstance(n, ast.JoinedStr):
            if not in_joined and any(has_cjk_const(v) for v in n.values) and not skip_ctx(n):
                if in_func(n) and _wrap_joined(n):
                    return
                if not in_func(n):
                    report.append((path, n.lineno, "module/default-level f-string"))
            for v in n.values:
                if isinstance(v, ast.FormattedValue):
                    visit(v.value, True)
            return
        if has_cjk_const(n) and not skip_ctx(n) and n.value not in SKIP:
            if in_func(n):
                edits.append((pos(n.lineno, n.col_offset), pos(n.end_lineno, n.end_col_offset), b"tr(" + seg(n) + b")")); return
            report.append((path, n.lineno, n.value[:30]))
        for c in ast.iter_child_nodes(n):
            visit(c, in_joined)

    def _wrap_joined(n):
        tpl, args = "", []
        for v in n.values:
            if isinstance(v, ast.Constant):
                tpl += v.value.replace("{", "{{").replace("}", "}}")
            else:
                spec = ""
                if v.format_spec is not None:
                    if not all(isinstance(x, ast.Constant) for x in v.format_spec.values): report.append((path, n.lineno, "complex format spec")); return False
                    spec = ":" + "".join(x.value for x in v.format_spec.values)
                conv = {-1: "", 115: "!s", 114: "!r", 97: "!a"}[v.conversion]
                tpl += "{" + str(len(args)) + conv + spec + "}"
                args.append(seg(v.value).decode("utf-8"))
        # 引数内に未処理のCJK文字列があれば次のパスで処理される
        new = "tr(" + json.dumps(tpl, ensure_ascii=False) + "".join(", " + a for a in args) + ")"
        edits.append((pos(n.lineno, n.col_offset), pos(n.end_lineno, n.end_col_offset), new.encode("utf-8"))); return True

    # クラス直下の title = "日本語" は N_() で包む（表示時に tr）
    for c in ast.walk(tree):
        if isinstance(c, ast.ClassDef):
            for st in c.body:
                if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) and st.targets[0].id == "title" and has_cjk_const(st.value):
                    edits.append((pos(st.value.lineno, st.value.col_offset), pos(st.value.end_lineno, st.value.end_col_offset), b"N_(" + seg(st.value) + b")"))
    visit(tree)
    # 外側優先: 入れ子の編集は捨てる（次のパスで処理）
    edits.sort(key=lambda e: (e[0], -e[1])); kept, end = [], -1
    for e in edits:
        if e[0] >= end: kept.append(e); end = e[1]
    for a, b, rep in sorted(kept, reverse=True):
        src = src[:a] + rep + src[b:]
    changed = bool(kept)
    if changed:
        t = src.decode("utf-8")
        imp = "from .i18n import tr, N_" if "/core/" in path.replace("\\", "/") else "from ..core.i18n import tr, N_"
        if imp not in t and "from .i18n import tr" not in t:
            m = re.search(r"(?m)^from __future__ import annotations\n", t)
            t = (t[:m.end()] + imp + "\n" + t[m.end():]) if m else imp + "\n" + t
        src = t.encode("utf-8")
        open(path, "wb").write(src)
    return changed


if __name__ == "__main__":
    for f in sys.argv[1:]:
        for i in range(6):
            if not process(f): break
    for r in report: print("MANUAL", *r)
