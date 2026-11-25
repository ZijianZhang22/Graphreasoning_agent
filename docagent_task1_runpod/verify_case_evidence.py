#!/usr/bin/env python3
"""Independently audit four pinned historical changes from the upstream cache.

Run after: bash launch.sh validate "$PWD/cases.json"
This checks Git source evidence. It does not call a model or run pytest.
"""
import argparse
import ast
import json
import subprocess
from pathlib import Path

def src(cache, case, commit, path):
    repo = cache / case
    p = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=repo,
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout if p.returncode == 0 else None

def definition(source, name):
    if source is None:
        return None
    tree = ast.parse(source)
    return next((node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name), None)

def ctor_params(source, class_name="Retry"):
    tree = ast.parse(source)
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == class_name)
    fn = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == "__init__")
    return {x.arg for x in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]}

def run(cache):
    cases = {}
    w_s, w_t = "d9caf5b88cc2a5247de779bd13a69b63d60bd1c4", "0e2cd5013f29cf18eef124e2061929c7cdb2df25"
    path = "werkzeug/_internal.py"
    assert definition(src(cache, "C01", w_s, path), "_dump_date")
    assert not definition(src(cache, "C01", w_t, path), "_dump_date")
    assert definition(src(cache, "C01", w_t, "werkzeug/http.py"), "_dump_date")
    cases["C01"] = "PASS: _dump_date moved from werkzeug/_internal.py to werkzeug/http.py"

    u_s, u_t = "9b95f29c575d73260ec4f5a8c0ea368cf242019e", "6446fef0cf432ca035169602a1447a0d8ef53e80"
    path = "src/urllib3/util/retry.py"
    before = ctor_params(src(cache, "C02", u_s, path))
    after = ctor_params(src(cache, "C02", u_t, path))
    assert "method_whitelist" in before
    assert "method_whitelist" not in after
    assert "allowed_methods" in after
    cases["C02"] = "PASS: Retry.__init__ renamed method_whitelist to allowed_methods"

    i_s, i_t = "f685200bda58808ca78735372e6d39fee971c00d", "c493cd846e9dc4750e07c9e46785d265e26bf2ca"
    old = "tests/test_serializer.py"
    new = "tests/test_itsdangerous/test_serializer.py"
    old_text = src(cache, "C03", i_s, old)
    new_text = src(cache, "C03", i_t, new)
    assert definition(old_text, "TestSerializer")
    assert not src(cache, "C03", i_t, old)
    assert definition(new_text, "TestSerializer")
    assert old_text == new_text
    cases["C03"] = "PASS: serializer test file renamed, class preserved"

    p_s, p_t = "00bed2f909a40aee9a7b3d2a13dd37f8054d3928", "c54b977c7ebf379f957db1cf7ce776608c67a521"
    path = "src/sample/simple.py"
    before = src(cache, "C04", p_s, path)
    after = src(cache, "C04", p_t, path)
    assert before is not None and after is not None and before != after
    assert ast.dump(ast.parse(before)) == ast.dump(ast.parse(after))
    assert definition(after, "add_one")
    cases["C04"] = "PASS: changed source bytes but exact same executable AST"
    return cases

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True,
                        help="Directory with C01/C02/C03/C04 source clones from cases.py validate")
    a = parser.parse_args()
    for name in ["C01", "C02", "C03", "C04"]:
        if not (a.cache / name).exists():
            parser.error(f"missing {a.cache/name}, first run: bash launch.sh validate \"$PWD/cases.json\"")
    try:
        results = run(a.cache)
    except (AssertionError, SyntaxError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"CASE HISTORY AUDIT FAILED: {type(exc).__name__}: {exc}") from exc
    for message in results.values():
        print(message)
    print(json.dumps({"source_audit_passed": True, "case_count": len(results)}, indent=2))

if __name__ == "__main__":
    main()
