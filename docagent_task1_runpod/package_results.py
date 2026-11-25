#!/usr/bin/env python3
"""Create an auditable ZIP of Task 1 inputs, logs, traces, patches and results."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SOURCES = (
    "README.md", "CASE_EVIDENCE.md", "cases.json", "cases.evaluator.json",
    "backend.runpod.json", "launch.sh", "run_all.sh",
    "package_results.py", "verify_case_evidence.py", "summarize.py",
)
ATTEMPT_FILES = (
    "summary.json", "ledger.jsonl", "packet_initial.md", "packet_final.md",
    "patch.diff", "agent.events.jsonl", "agent.result.json", "prompt.txt",
)
LIMIT = 4 * 1024 * 1024


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def git_head(path):
    if not (path / ".git").exists():
        return None
    try:
        p = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return p.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def manifest_status(batch, source, upstream, model):
    cases = read_json(source / "cases.json").get("cases", [])
    stages = {}
    stages_path = batch / "stage_status.tsv"
    if stages_path.is_file():
        for line in stages_path.read_text(encoding="utf-8").splitlines()[1:]:
            fields = line.split("\t")
            if len(fields) >= 2:
                stages[fields[0]] = fields[1]
    rows, missing, mismatched = [], [], []
    for case in cases:
        cid = case["case_id"]
        attempt_root = batch / "runs" / "real" / cid / "attempts"
        latest = {}
        if attempt_root.is_dir():
            for file in sorted(attempt_root.glob("*/summary.json")):
                item = read_json(file)
                arm = item.get("arm")
                if arm not in {"blind", "checked"}:
                    continue
                key = (item.get("finished_at") or "", item.get("attempt_id") or "")
                if arm not in latest or key >= latest[arm][0]:
                    latest[arm] = (key, item)
        arms = {arm: record for arm, (_, record) in latest.items()}
        for arm in ("blind", "checked"):
            item = arms.get(arm, {})
            if not item:
                missing.append(cid + "/" + arm)
            rows.append({
                "case_id": cid,
                "arm": arm,
                "attempt_id": item.get("attempt_id"),
                "is_live": item.get("is_live") is True,
                "model": (item.get("backend") or {}).get("model"),
                "terminal_status": item.get("status"),
                "oracle_verdict": (item.get("oracle") or {}).get("verdict"),
                "initial_packet_sha256": item.get("packet_initial_sha256"),
            })
        if all(arm in arms for arm in ("blind", "checked")):
            a = arms["blind"].get("packet_initial_sha256")
            b = arms["checked"].get("packet_initial_sha256")
            if not a or a != b:
                mismatched.append(cid)
    count = sum(row["is_live"] for row in rows)
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "requested_model": model,
        "docagent_sha": git_head(upstream),
        "experiment_wrapper_sha": git_head(source.parent),
        "case_ids": [case["case_id"] for case in cases],
        "expected_live_sessions": 2 * len(cases),
        "observed_live_sessions": count,
        "all_sessions_recorded_live": count == 2 * len(cases) and not missing,
        "missing_arms": missing,
        "initial_packet_mismatches": mismatched,
        "stages": stages,
        "arms": rows,
        "provenance": "historical natural commits; researcher-authored notes and tasks",
        "interpretation": (
            "Live sessions do NOT imply a successful solution; use oracle_verdict. "
            "C01 and C03 grade localization answers; C03 does not execute pytest. "
            "The checker is experimental and not part of the released DocAgent skill."
        ),
    }


def selected_files(batch, source):
    for name in SOURCES:
        path = source / name
        if path.is_file() and not path.is_symlink():
            yield path, "inputs/" + name
    for name in ("run_info.txt", "stage_status.tsv"):
        path = batch / name
        if path.is_file() and not path.is_symlink():
            yield path, name
    for path in sorted((batch / "logs").glob("*")):
        if path.is_file() and not path.is_symlink():
            yield path, "logs/" + path.name
    for group in ("real", "demo"):
        group_dir = batch / "runs" / group
        if not group_dir.is_dir():
            continue
        for case_dir in sorted(group_dir.glob("C*")):
            if not case_dir.is_dir():
                continue
            for name in ("case.json", "report.md"):
                path = case_dir / name
                if path.is_file() and not path.is_symlink():
                    yield path, f"runs/{group}/{case_dir.name}/{name}"
            for attempt in sorted((case_dir / "attempts").glob("*")):
                if not attempt.is_dir():
                    continue
                for name in ATTEMPT_FILES:
                    path = attempt / name
                    if path.is_file() and not path.is_symlink():
                        yield path, f"runs/{group}/{case_dir.name}/attempts/{attempt.name}/{name}"
        for sub in ("reports", "summary"):
            for path in sorted((group_dir / sub).glob("*")):
                if path.is_file() and not path.is_symlink() and path.suffix in {".md", ".csv", ".json"}:
                    yield path, f"runs/{group}/{sub}/{path.name}"


def build_zip(batch, source, upstream, model, target):
    status = manifest_status(batch, source, upstream, model)
    prefix = "DocAgent_Task1_results/"
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".zip.partial")
    digests = []
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for file, name in selected_files(batch, source):
            if file.stat().st_size > LIMIT:
                status.setdefault("excluded_large_files", []).append(name)
                continue
            contents = file.read_bytes()
            archive.writestr(prefix + name, contents)
            digests.append((hashlib.sha256(contents).hexdigest(), name))
        contents = (json.dumps(status, indent=2, ensure_ascii=False) + "\n").encode()
        archive.writestr(prefix + "batch_status.json", contents)
        digests.append((hashlib.sha256(contents).hexdigest(), "batch_status.json"))
        guide = (
            "# How to read this archive\n\n"
            "Start with batch_status.json: it flags missing arms and actual model sessions.\n"
            "Read runs/real/summary/task1_summary.csv and the four case reports.\n"
            "Inspect attempt summary.json, ledger.jsonl and patch.diff for evidence.\n"
            "Failed and incomplete experiments remain labeled, never filled with fake data.\n"
            "The Git histories are natural, but the stale notes were written for this study.\n"
            "The ZIP omits Git checkouts, model weights, hidden caches and credential files.\n"
        ).encode()
        archive.writestr(prefix + "HOW_TO_READ.md", guide)
        digests.append((hashlib.sha256(guide).hexdigest(), "HOW_TO_READ.md"))
        archive.writestr(prefix + "SHA256SUMS.txt", "".join(
            f"{digest}  {name}\n" for digest, name in digests
        ))
    with zipfile.ZipFile(temp) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP integrity check failed: {bad}")
    temp.replace(target)
    print(f"ZIP saved: {target} ({target.stat().st_size:,} bytes)")
    print(f"Live sessions: {status['observed_live_sessions']}/{status['expected_live_sessions']}")
    print(f"Missing arms: {status['missing_arms']}")
    print(f"Packet mismatches: {status['initial_packet_mismatches']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if not args.batch.is_dir():
        parser.error(f"batch not found: {args.batch}")
    build_zip(args.batch, args.sources, args.upstream, args.model, args.out)


if __name__ == "__main__":
    main()
