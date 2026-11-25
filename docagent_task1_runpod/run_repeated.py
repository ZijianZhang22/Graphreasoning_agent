#!/usr/bin/env python3
"""Run original Xiangrui Task 1 four cases in three seeded paired rounds.

The original case manifest, prompt, checker, oracle, and driver stay unchanged.
Optional extra cases are a SEPARATE track. Failed runs remain logged and missing
sessions are never fabricated. Creates one ZIP with raw traces and summaries.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("DOCAGENT_WORKDIR", "/workspace/docagent-task1")).resolve()
UPSTREAM = Path(os.environ.get("DOCAGENT_UPSTREAM_DIR", str(WORK / "DocAgent"))).resolve()
DRIVER = UPSTREAM / "experiments/case_studies/cases.py"
SEEDS = (20261119, 20261120, 20261121)
PRIMARY = ("C01", "C02", "C03", "C04")
OPTIONAL = ("C05", "C06")


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git_rev(path):
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def step(batch, name, command, steps):
    print("\n=== " + name + " ===", flush=True)
    print("$ " + " ".join(map(str, command)), flush=True)
    start = time.monotonic()
    log_file = batch / "logs" / (name + ".log")
    try:
        with log_file.open("w", encoding="utf-8") as log:
            p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace", bufsize=1)
            for line in p.stdout:
                log.write(line)
                print(line, end="", flush=True)
            rc = p.wait()
    except (OSError, ValueError) as e:
        rc = 127
        log_file.write_text(str(e) + "\n", encoding="utf-8")
    steps.append({"stage": name, "returncode": rc, "duration_seconds": round(time.monotonic()-start, 2)})
    write(batch / "steps.json", {"steps": steps})
    print(name + (": OK" if rc == 0 else ": FAILED"), flush=True)
    return rc == 0


def backend(batch, seed):
    cfg = load(HERE / "backend.runpod.json")
    assert cfg.get("command"), "backend.runpod.json missing command"
    cfg["name"] = "task1-repeated-seed-" + str(seed)
    cfg["settings"].update(model="qwen3:8b", seed=seed, temperature=0,
                           think=False, api_style="ollama",
                           base_url="http://127.0.0.1:11434", location="runpod")
    dest = batch / "config" / ("backend_" + str(seed) + ".json")
    write(dest, cfg)
    return dest


def manifest_check(path, expected):
    ids = [x["case_id"] for x in load(path).get("cases", [])]
    assert ids == list(expected), f"case IDs in {path}: expected {expected}, got {ids}"
    assert path.with_name(path.stem + ".evaluator.json").is_file(), "missing evaluator file"


def report(batch, rounds, with_extra):
    sessions, pairs = [], []
    tracks = [("primary", PRIMARY)]
    if with_extra:
        tracks.append(("extra", OPTIONAL))
    for track, ids in tracks:
        for repeat in range(1, rounds+1):
            seed = SEEDS[repeat-1]
            for case in ids:
                root = batch / "runs" / track / ("round_%02d" % repeat) / case / "attempts"
                saved = {}
                for item in sorted(root.glob("*/summary.json")) if root.exists() else []:
                    result = load(item)
                    arm = result.get("arm")
                    if arm in ("blind", "checked"):
                        saved[arm] = result
                pair = {}
                for arm in ("blind", "checked"):
                    item = saved.get(arm, {})
                    truth = (item.get("oracle") or {}).get("verdict", "missing")
                    row = {
                        "track": track, "round": repeat, "case": case, "arm": arm,
                        "seed": seed, "attempt_id": item.get("attempt_id", ""),
                        "live": item.get("is_live") is True,
                        "model": (item.get("backend") or {}).get("model", ""),
                        "status": item.get("status", "missing"), "oracle": truth,
                        "passed": item.get("is_live") is True and truth == "pass",
                        "actions": item.get("actions"),
                        "elapsed_ms": (item.get("timing") or {}).get("wall_ms"),
                        "initial_hash": item.get("packet_initial_sha256", ""),
                        "check_action": (item.get("check") or {}).get("policy_action", ""),
                    }
                    sessions.append(row)
                    pair[arm] = row
                blind, checked = pair["blind"], pair["checked"]
                matched = (blind["live"] and checked["live"] and
                           bool(blind["initial_hash"]) and
                           blind["initial_hash"] == checked["initial_hash"])
                outcome = "incomplete"
                if matched:
                    if blind["passed"] and checked["passed"]:
                        outcome = "both_pass"
                    elif blind["passed"]:
                        outcome = "regressed"
                    elif checked["passed"]:
                        outcome = "improved"
                    else:
                        outcome = "both_fail"
                pairs.append({"track": track, "round": repeat, "case": case,
                              "seed": seed, "matched": matched, "outcome": outcome,
                              "blind_oracle": blind["oracle"], "checked_oracle": checked["oracle"],
                              "hashes_match": bool(blind["initial_hash"]) and
                              blind["initial_hash"] == checked["initial_hash"]})
    case_rows = []
    for track, ids in tracks:
        for case in ids:
            for arm in ("blind", "checked"):
                subset = [x for x in sessions if x["track"] == track and x["case"] == case and x["arm"] == arm]
                live = [x for x in subset if x["live"]]
                passed = sum(x["passed"] for x in live)
                case_rows.append({"track": track, "case": case, "arm": arm,
                                  "expected": rounds, "live": len(live), "passed": passed,
                                  "rate_live": round(passed / len(live), 3) if live else None})
    overall = {}
    for track, ids in tracks:
        s = [x for x in sessions if x["track"] == track]
        p = [x for x in pairs if x["track"] == track]
        overall[track] = {
            "expected_sessions": len(ids) * rounds * 2,
            "live_sessions": sum(x["live"] for x in s),
            "matched_pairs": sum(x["matched"] for x in p),
            "expected_pairs": len(p),
            "paired_outcomes": dict(Counter(x["outcome"] for x in p)),
        }
    summary = {
        "design": "Xiangrui Task 1 unchanged required cases; repeated paired runs",
        "rounds": rounds, "seeds": list(SEEDS[:rounds]), "temperature": 0,
        "seed_policy": "same seed for the two arms in a round, different fixed seed each round",
        "overall": overall, "case_stats": case_rows, "paired_runs": pairs,
        "limits": ["Temperature 0 can produce identical outputs despite seed changes.",
                   "Pair outcomes describe these cases, not a prevalence or statistical population.",
                   "Tool traces, not oracle failure alone, are required to argue stale-memory reliance.",
                   "Optional cases are kept separate and contain extracted notes, not verbatim historic user memory."],
    }
    dest = batch / "analysis"
    write(dest / "stability.json", summary)
    for name, rows in [("sessions.csv", sessions), ("pairs.csv", pairs), ("case_rates.csv", case_rows)]:
        with (dest / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
            if rows:
                w.writeheader()
                w.writerows(rows)
    lines = ["# Task 1 repeated evaluations", "",
             "Fixed cases C01-C04, same tasks and oracles as the initial experiment.",
             "Three rounds by default; temperature=0. Fixed round seeds.",
             "", "| Case | Blind pass / live | Checked pass / live | Pair outcomes |",
             "|---|---|---|---|"]
    for case in PRIMARY:
        x = {r["arm"]: r for r in case_rows if r["track"] == "primary" and r["case"] == case}
        counts = Counter(r["outcome"] for r in pairs if r["track"] == "primary" and r["case"] == case)
        lines.append(f"| {case} | {x['blind']['passed']}/{x['blind']['live']} | "
                     f"{x['checked']['passed']}/{x['checked']['live']} | {dict(counts)} |")
    lines.extend(["", "## Completeness", "",
                  f"Primary live sessions: {overall['primary']['live_sessions']}/{overall['primary']['expected_sessions']}.",
                  f"Matched pairs: {overall['primary']['matched_pairs']}/{overall['primary']['expected_pairs']}.",
                  "No missing sessions were filled with synthetic data."])
    if with_extra:
        lines.extend(["", "## Optional extension (separate from primary)", "",
                      f"Live sessions: {overall['extra']['live_sessions']}/{overall['extra']['expected_sessions']}.",
                      "C05/C06 are not pooled with C01-C04."])
    (dest / "stability.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def archive(batch, path):
    prefix = "DocAgent_Task1_repeated/"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".zip.partial")
    digests = []
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as zipf:
        def put(file, name):
            if not file.is_file() or file.is_symlink() or file.stat().st_size > 4*1024*1024:
                return
            content = file.read_bytes()
            zipf.writestr(prefix + name, content)
            digests.append((hashlib.sha256(content).hexdigest(), name))
        for file in sorted(HERE.iterdir()):
            if file.name in ("README.md", "CASE_EVIDENCE.md", "EXTRA_CASE_EVIDENCE.md",
                             "cases.json", "cases.evaluator.json",
                             "cases.extra.json", "cases.extra.evaluator.json",
                             "backend.runpod.json", "launch.sh", "run_all.sh",
                             "run_repeated.py", "package_results.py",
                             "verify_case_evidence.py", "summarize.py"):
                put(file, "inputs/" + file.name)
        for file in sorted(batch.rglob("*")):
            if file.is_file():
                put(file, file.relative_to(batch).as_posix())
        zipf.writestr(prefix + "SHA256SUMS.txt", "".join(
            f"{digest}  {name}\n" for digest, name in digests))
    with zipfile.ZipFile(tmp) as zipf:
        assert zipf.testzip() is None, "ZIP integrity check failed"
    tmp.replace(path)
    print(f"\nRESULT ZIP: {path} ({path.stat().st_size:,} bytes)", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rounds", type=int, choices=(1, 2, 3), default=3)
    p.add_argument("--extra", action="store_true", help="include optional C05-C06, reported separately")
    p.add_argument("--skip-setup", action="store_true", help="Ollama and pinned DocAgent already installed")
    args = p.parse_args()
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + str(os.getpid())
    batch = WORK / "repeat_batches" / label
    (batch / "logs").mkdir(parents=True, exist_ok=False)
    target = WORK / "exports" / ("DocAgent_Task1_Repeated_" + label + ".zip")
    stages, failed = [], False
    meta = {"rounds": args.rounds, "extra": args.extra, "model": "qwen3:8b",
            "wrapper_commit": git_rev(HERE.parent), "upstream_commit": git_rev(UPSTREAM),
            "started_at": datetime.now(timezone.utc).isoformat(), "success": False}
    try:
        manifest_check(HERE / "cases.json", PRIMARY)
        if args.extra:
            manifest_check(HERE / "cases.extra.json", OPTIONAL)
        if not args.skip_setup and not step(batch, "00_setup", ["bash", str(HERE / "launch.sh"), "setup"], stages):
            raise RuntimeError("setup failed")
        if not DRIVER.is_file():
            raise RuntimeError(f"Driver missing at {DRIVER}; omit --skip-setup to install")
        if not step(batch, "01_smoke", ["bash", str(HERE / "launch.sh"), "smoke"], stages):
            raise RuntimeError("smoke failed")
        for track, manifest in [("primary", HERE / "cases.json")] + (
                [("extra", HERE / "cases.extra.json")] if args.extra else []):
            cmd = [sys.executable, str(DRIVER), "validate", "--manifest", str(manifest),
                   "--cache", str(WORK / "cache")]
            if not step(batch, "02_validate_" + track, cmd, stages):
                raise RuntimeError(track + " validation failed")
        if not step(batch, "03_source_audit",
                    [sys.executable, str(HERE / "verify_case_evidence.py"),
                     "--cache", str(WORK / "cache")], stages):
            raise RuntimeError("source audit failed")
        if not step(batch, "04_ollama", ["ollama", "list"], stages):
            raise RuntimeError("Ollama unavailable")
        for n in range(1, args.rounds + 1):
            cfg = backend(batch, SEEDS[n-1])
            for track, ids, manifest in [("primary", PRIMARY, HERE / "cases.json")] + (
                    [("extra", OPTIONAL, HERE / "cases.extra.json")] if args.extra else []):
                out = batch / "runs" / track / ("round_%02d" % n)
                out.mkdir(parents=True)
                for cid in ids:
                    cmd = [sys.executable, str(DRIVER), "run", "--case", cid, "--arm", "both",
                           "--manifest", str(manifest), "--backend-config", str(cfg),
                           "--out", str(out), "--cache", str(WORK / "cache"),
                           "--time-s", os.environ.get("TASK1_TIME_S", "180"),
                           "--max-actions", os.environ.get("TASK1_ACTIONS", "8")]
                    if not step(batch, f"r{n}_{track}_{cid}", cmd, stages):
                        failed = True
                if not step(batch, f"report_r{n}_{track}",
                            [sys.executable, str(DRIVER), "report", "--runs", str(out),
                             "--out", str(batch / "reports" / track / ("round_%02d" % n))], stages):
                    failed = True
        info = report(batch, args.rounds, args.extra)
        meta["results"] = info["overall"]
        meta["success"] = not failed and info["overall"]["primary"]["live_sessions"] == 8 * args.rounds
    except Exception as e:
        failed = True
        meta["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        try:
            if not (batch / "analysis" / "stability.json").exists():
                info = report(batch, args.rounds, args.extra)
                meta["results"] = info["overall"]
        except Exception as e:
            meta["report_error"] = repr(e)
            failed = True
        meta["steps"] = stages
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(batch / "batch_status.json", meta)
        try:
            archive(batch, target)
        except Exception:
            failed = True
            traceback.print_exc()
        print("RAW DATA:", batch, flush=True)
        print("ZIP:", target, flush=True)
        if "results" in meta:
            print("PRIMARY LIVE SESSIONS:",
                  meta["results"]["primary"]["live_sessions"], "/",
                  meta["results"]["primary"]["expected_sessions"], flush=True)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
