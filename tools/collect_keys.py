"""tr()/N_() の定数キーを収集する（翻訳漏れテストでも使用）。"""
import ast, glob, os

def collect(root="polaris"):
    keys = []
    for f in sorted(glob.glob(os.path.join(root, "**", "*.py"), recursive=True)):
        if f.endswith("i18n_en.py"): continue
        tree = ast.parse(open(f, encoding="utf-8").read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("tr", "N_") and n.args \
               and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                k = n.args[0].value
                if k not in keys: keys.append(k)
    return keys

if __name__ == "__main__":
    ks = collect()
    import json
    json.dump(ks, open("/tmp/keys.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(len(ks), "keys", sum(len(k) for k in ks), "chars")
