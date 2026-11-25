#!/usr/bin/env python3
"""Supplement Xiangrui's Task 1 with source behavior checks and offline replay.

This does NOT modify cases.json, the original case runner, prompts, or any
previous agent session. It reads already cloned cached repos, exports pinned
Git snapshots, probes C02 behavior, collects C03 pytest selectors at both
versions, audits C01/C04 source evidence, and separately retries the *released*
DocAgent file-level helper in a worktree. Missing dependencies are explicitly
reported, never counted as successful evidence.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("DOCAGENT_WORKDIR", "/workspace/docagent-task1")).resolve()
UPSTREAM = Path(os.environ.get("DOCAGENT_UPSTREAM_DIR", str(WORK / "DocAgent"))).resolve()
CASES = HERE / "cases.json"
CACHE = WORK / "cache"
HELPER = UPSTREAM / "skills/docagent/scripts/docagent.py"
DRIVER = UPSTREAM / "experiments/case_studies/cases.py"
MAX_BYTES = 4096


def run(args, cwd=None, env=None, timeout=90):
    try:
        p = subprocess.run(args, cwd=cwd, env=env, timeout=timeout,
                           text=True, encoding="utf-8", errors="replace",
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return {"command": list(map(str, args)), "exit_code": p.returncode,
                "stdout": p.stdout[-MAX_BYTES:], "stderr": p.stderr[-MAX_BYTES:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": list(map(str, args)), "exit_code": None,
                "stdout": "", "stderr": str(exc), "infrastructure_error": type(exc).__name__}


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def show(repo, revision, path):
    # Source must not be clipped: full AST required for both ownership and
    # no-op-change verification. The generic logging helper clips stdout.
    try:
        p = subprocess.run(["git", "-C", str(repo), "show", f"{revision}:{path}"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90)
        return p.stdout if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def export_tree(repo, rev, dest):
    p = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", rev],
                       capture_output=True, timeout=120, check=True)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        for item in tf:
            rel = Path(item.name)
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("unsafe Git archive entry")
            target = dest / rel
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(item) as inp, target.open("wb") as out:
                    out.write(inp.read())
    return dest


def ast_lines(src, name):
    if src is None:
        return None
    try:
        tree = ast.parse(src)
        return [x.lineno for x in tree.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))
                and x.name == name]
    except SyntaxError:
        return None


def inspect_c01(case):
    repo = CACHE / "C01"
    old = show(repo, case["s"], "werkzeug/_internal.py")
    new = show(repo, case["t"], "werkzeug/http.py")
    old_current = show(repo, case["t"], "werkzeug/_internal.py")
    result = {
        "old_owner_lines": ast_lines(old, "_dump_date"),
        "current_owner_lines": ast_lines(new, "_dump_date"),
        "old_file_still_defines_symbol": bool(ast_lines(old_current, "_dump_date")),
        "cookie_date_calls_current_symbol": bool(new and re.search(
            r"def cookie_date\b[\s\S]*?return _dump_date\(", new)),
        "http_date_calls_current_symbol": bool(new and re.search(
            r"def http_date\b[\s\S]*?return _dump_date\(", new)),
        "source_s": case["s"], "source_t": case["t"],
    }
    result["supported"] = (bool(result["old_owner_lines"]) and
                           bool(result["current_owner_lines"]) and
                           not result["old_file_still_defines_symbol"] and
                           result["cookie_date_calls_current_symbol"] and
                           result["http_date_calls_current_symbol"])
    return result


def inspect_c04(case):
    repo = CACHE / "C04"
    a = show(repo, case["s"], case["claim"]["covered_path"])
    b = show(repo, case["t"], case["claim"]["covered_path"])
    if a is None or b is None:
        return {"supported": False, "error": "source blob unavailable"}
    old_ast = ast.dump(ast.parse(a), include_attributes=False)
    new_ast = ast.dump(ast.parse(b), include_attributes=False)
    return {"source_s": case["s"], "source_t": case["t"],
            "raw_bytes_changed": a != b,
            "ast_equal": old_ast == new_ast,
            "supported": a != b and old_ast == new_ast}


def retry_probe(snapshot):
    # Older urllib3 vendors six 1.12, which registers a PEP 302-only
    # meta-path importer. Modern Python can require find_spec (PEP 451).
    # Adapt the *interpreter's* import mechanism for that legacy finder;
    # do not modify the pinned repository or Retry implementation.
    legacy_import_shim = (
        "import importlib.util, sys\n"
        "class _LegacySixFinderShim:\n"
        "  def find_spec(self, fullname, path=None, target=None):\n"
        "    for finder in tuple(sys.meta_path):\n"
        "      if type(finder).__name__ == '_SixMetaPathImporter':\n"
        "        old = finder.find_module(fullname, path)\n"
        "        if old is not None:\n"
        "          return importlib.util.spec_from_loader(fullname, old, is_package=old.is_package(fullname))\n"
        "    return None\n"
        "sys.meta_path.insert(0, _LegacySixFinderShim())\n"
    )
    code = legacy_import_shim + (
        "import json, warnings, urllib3\n"
        "from urllib3.util.retry import Retry\n"
        "warnings.simplefilter('ignore', DeprecationWarning)\n"
        "def probe(name, **kw):\n"
        "  try:\n"
        "    r=Retry(**kw)\n"
        "    return {'accepted':True, 'allowed_methods':sorted(r.allowed_methods) if r.allowed_methods else None}\n"
        "  except Exception as e:\n"
        "    return {'accepted':False, 'exception':type(e).__name__, 'message':str(e)[:240]}\n"
        "print(json.dumps({'module_file':urllib3.__file__,\n"
        "  'old_keyword':probe('old',method_whitelist=frozenset(['GET','HEAD'])),\n"
        "  'new_keyword':probe('new',allowed_methods=frozenset(['GET','HEAD']))}))\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(snapshot / "src")
    result = run([sys.executable, "-c", code], cwd=snapshot, env=env, timeout=40)
    result["legacy_six_compatibility_shim"] = True
    result["compatibility_note"] = ("PEP 302 to 451 importer adapter in subprocess only; "
                                   "the pinned repo and Retry behavior are untouched.")
    try:
        data = json.loads(result["stdout"].strip().splitlines()[-1])
        expected_root = str((snapshot / "src").resolve())
        result["observed"] = data
        result["loaded_current_snapshot"] = str(data.get("module_file", "")).startswith(expected_root)
    except (IndexError, ValueError, KeyError):
        result["observed"] = None
        result["loaded_current_snapshot"] = False
    return result


def pytest_collect(snapshot, selector):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(snapshot / "src")
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = run([sys.executable, "-m", "pytest", "-q", "--collect-only",
                  "-p", "no:cacheprovider", selector],
                 cwd=snapshot, env=env, timeout=60)
    lines = result.get("stdout", "").splitlines()
    nodeids = [s.strip() for s in lines if s.strip().startswith("tests/") and "::" in s]
    found = re.findall(r"(\d+)\s+tests?\s+collected", result["stdout"])
    result["selector"] = selector
    result["collected_count"] = int(found[-1]) if found else (len(nodeids) if result["exit_code"] == 0 else None)
    result["node_ids"] = nodeids[:80]
    result["node_ids_truncated"] = max(0, len(nodeids) - 80)
    result["completed"] = result["exit_code"] is not None
    return result


def inspect_c02(case, out):
    repo = CACHE / "C02"
    records = {}
    with tempfile.TemporaryDirectory(prefix="task1-c02-") as td:
        root = Path(td)
        for label in ("s", "t"):
            try:
                tree = export_tree(repo, case[label], root / label)
                records[label] = retry_probe(tree)
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                records[label] = {"infrastructure_error": str(exc)}
    before = records["s"].get("observed") or {}
    after = records["t"].get("observed") or {}
    records["behavior_verified"] = bool(
        records["s"].get("loaded_current_snapshot") and
        records["t"].get("loaded_current_snapshot") and
        before.get("old_keyword", {}).get("accepted") is True and
        after.get("old_keyword", {}).get("accepted") is False and
        after.get("old_keyword", {}).get("exception") == "TypeError" and
        after.get("new_keyword", {}).get("accepted") is True
    )
    if not records["behavior_verified"]:
        records["incomplete_reason"] = (
            "Old and new runtime acceptance not both confirmed. Inspect s/t stderr "
            "and loaded_current_snapshot before reporting a behavior pass."
        )
    save(out / "C02_api_behavior.json", records)
    return records


def inspect_c03(case, out):
    repo = CACHE / "C03"
    old_sel = "tests/test_serializer.py::TestSerializer"
    new_sel = "tests/test_itsdangerous/test_serializer.py::TestSerializer"
    records = {"old_selector": old_sel, "current_selector": new_sel}
    with tempfile.TemporaryDirectory(prefix="task1-c03-") as td:
        root = Path(td)
        try:
            src_old = export_tree(repo, case["s"], root / "s")
            src_new = export_tree(repo, case["t"], root / "t")
            records["s_old_selector"] = pytest_collect(src_old, old_sel)
            records["t_old_selector"] = pytest_collect(src_new, old_sel)
            records["t_new_selector"] = pytest_collect(src_new, new_sel)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            records["infrastructure_error"] = str(exc)
    old = records.get("s_old_selector", {})
    stale = records.get("t_old_selector", {})
    current = records.get("t_new_selector", {})
    records["collection_verified"] = (
        old.get("exit_code") == 0 and (old.get("collected_count") or 0) > 0 and
        stale.get("exit_code") not in (0, None) and
        current.get("exit_code") == 0 and (current.get("collected_count") or 0) > 0
    )
    if any("No module named pytest" in x.get("stderr", "") for x in
           (old, stale, current)):
        records["incomplete_reason"] = (
            "Missing pytest in the SAME interpreter used by audit_task1_evidence.py "
            f"({sys.executable}); install it there and repeat the audit."
        )
    save(out / "C03_pytest_collection.json", records)
    return records


def helper_gate(case):
    repo = CACHE / case["case_id"]
    evidence = {"case": case["case_id"], "mode": "released helper in shared-object worktree"}
    # Compare directly first; this is an independent diagnostic, NOT the released gate.
    probe = run(["git", "-C", str(repo), "diff", "--name-only",
                 "--diff-filter=ACMRD", case["s"], case["t"]])
    evidence["direct_git_diff"] = probe
    # Git rename detection often reports only the destination name, while
    # the old covered path no longer exists. Do not mislabel this as a
    # release-gate detection. Keep separate path-existence evidence.
    old_path = case["claim"]["covered_path"]
    evidence["covered_path_exists_at_s"] = show(repo, case["s"], old_path) is not None
    evidence["covered_path_exists_at_t"] = show(repo, case["t"], old_path) is not None
    if not HELPER.is_file():
        evidence["error"] = f"missing released helper: {HELPER}"
        return evidence
    with tempfile.TemporaryDirectory(prefix="task1-gate-") as td:
        checkout = Path(td) / "worktree"
        created = run(["git", "-C", str(repo), "worktree", "add", "--detach",
                       "--quiet", str(checkout), case["t"]], timeout=120)
        evidence["worktree_command"] = created
        if created["exit_code"] != 0:
            return evidence
        try:
            spec = importlib.util.spec_from_file_location("task1_released_helper_audit", HELPER)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            changed = sorted(module.diff_since(checkout.resolve(), case["s"]))
            matching = sorted(p for p in changed if module.match_any(
                p, [case["claim"]["covered_path"]]))
            evidence.update({
                "released_helper_success": True, "changed_files": changed,
                "covered_file_changed": bool(matching), "changed_covered_files": matching,
                "helper_sha256": hashlib.sha256(HELPER.read_bytes()).hexdigest(),
            })
        except Exception as exc:
            evidence["released_helper_success"] = False
            evidence["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            evidence["cleanup"] = run(["git", "-C", str(repo), "worktree",
                                       "remove", "--force", str(checkout)])
    return evidence


def replay_saved(source_runs, output):
    results = {}
    if not DRIVER.is_file() or not source_runs.is_dir():
        return {"error": "Original driver or saved rounds unavailable"}
    for case in ("C01", "C02", "C03", "C04"):
        result = run([sys.executable, str(DRIVER), "replay", "--case", case,
                      "--runs", str(source_runs), "--offline",
                      "--out", str(output / "replayed")])
        regenerated = output / "replayed" / f"{case}.md"
        original = source_runs / "reports" / f"{case}.md"
        result["replay_file_created"] = regenerated.exists()
        # Replay output should not require any model call.
        result["replayed_sha256"] = hashlib.sha256(
            regenerated.read_bytes()).hexdigest() if regenerated.exists() else None
        results[case] = result
    return results


def make_zip(folder, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as arc:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                arc.write(p, p.relative_to(folder.parent))
        arc.write(__file__, "audit_task1_evidence.py")
    with zipfile.ZipFile(target) as arc:
        assert arc.testzip() is None
    return target


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=Path, help="saved 4-case run directory for offline replay")
    ap.add_argument("--out", type=Path, help="output folder (new or empty)")
    args = ap.parse_args()
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (args.out or (WORK / "acceptance_audits" / label)).resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(CASES.read_text(encoding="utf-8"))
    cases = {case["case_id"]: case for case in manifest["cases"]}
    status = {
        "name": "Task 1 supplemental evidence, not a rerun of Agent sessions",
        "timestamp_utc": label, "source_manifest": str(CASES),
        "cases": list(cases), "results": {}, "human_review": "pending",
    }
    try:
        for case in ("C01", "C02", "C03", "C04"):
            print("Auditing", case, flush=True)
            if not (CACHE / case / "HEAD").exists() and not (CACHE / case / ".git").exists():
                status["results"][case] = {"error": f"cached git repo missing: {CACHE / case}"}
                continue
            status["results"][case] = {"gate": helper_gate(cases[case])}
            if case == "C01":
                status["results"][case]["owner"] = inspect_c01(cases[case])
            elif case == "C02":
                status["results"][case]["behavior"] = inspect_c02(cases[case], out)
            elif case == "C03":
                status["results"][case]["pytest"] = inspect_c03(cases[case], out)
            elif case == "C04":
                status["results"][case]["unchanged_behavior"] = inspect_c04(cases[case])
            save(out / (case + "_gate.json"), status["results"][case]["gate"])
        source_runs = args.runs
        if source_runs is None:
            candidates = sorted(WORK.glob("repeat_batches/*/runs/primary/round_01"))
            source_runs = candidates[-1] if candidates else None
        if source_runs:
            status["saved_runs"] = str(source_runs)
            status["offline_replay"] = replay_saved(source_runs, out)
        else:
            status["offline_replay"] = {"error": "No saved run found. Set --runs path."}
    except Exception as exc:
        status["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        save(out / "audit_summary.json", status)
        target = out.parent / (out.name + ".zip")
        make_zip(out, target)
        print("AUDIT SUMMARY:", out / "audit_summary.json", flush=True)
        print("AUDIT ZIP:", target, flush=True)
        for case, result in status["results"].items():
            gate = result.get("gate", {})
            if case == "C02":
                special = result.get("behavior", {}).get("behavior_verified")
            elif case == "C03":
                special = result.get("pytest", {}).get("collection_verified")
            elif case == "C01":
                special = result.get("owner", {}).get("supported")
            else:
                special = result.get("unchanged_behavior", {}).get("supported")
            print(f"{case}: supplemental_check={special} released_gate={gate.get('released_helper_success')}")
        print("Human second-reviewer sign-off still PENDING.")
    return 1 if status.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
