#!/usr/bin/env python3
"""Summarize official DocAgent Task 1 case records without calling any model.

Only reports observed runs. Synthetic or fake sessions remain clearly labeled.
"""
import argparse
import csv
import json
from pathlib import Path

FIELDS = [
    "case_id", "category", "change_origin", "note_origin", "arm",
    "attempt_id", "is_live", "model", "terminal_status", "oracle_verdict",
    "actions", "wall_s", "input_tokens", "output_tokens", "check_status",
    "policy_action", "patch_bytes", "packet_initial_sha256",
]

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def collect(runs):
    rows = []
    mismatches = []
    for case_dir in sorted(runs.iterdir()):
        if not case_dir.is_dir() or not (case_dir / "case.json").is_file():
            continue
        meta = read_json(case_dir / "case.json")
        attempts = sorted((case_dir / "attempts").glob("*/summary.json")) if (case_dir / "attempts").exists() else []
        latest = {}
        for path in attempts:
            item = read_json(path)
            arm = item.get("arm")
            key = (item.get("finished_at", ""), item.get("attempt_id", ""))
            if arm not in latest or key > latest[arm][0]:
                latest[arm] = (key, item)
        by_arm = {arm: entry for arm, (_, entry) in latest.items()}
        if "blind" in by_arm and "checked" in by_arm:
            a = by_arm["blind"].get("packet_initial_sha256")
            b = by_arm["checked"].get("packet_initial_sha256")
            if not a or a != b:
                mismatches.append(meta["case_id"])
        for arm in ("blind", "checked"):
            item = by_arm.get(arm, {})
            backend = item.get("backend") or {}
            oracle = item.get("oracle") or {}
            usage = item.get("usage") or {}
            timing = item.get("timing") or {}
            check = item.get("check") or {}
            wall_ms = timing.get("wall_ms")
            rows.append({
                "case_id": meta["case_id"],
                "category": meta.get("category"),
                "change_origin": meta.get("change_origin"),
                "note_origin": meta.get("note_origin"),
                "arm": arm,
                "attempt_id": item.get("attempt_id", ""),
                "is_live": item.get("is_live", False),
                "model": backend.get("model", ""),
                "terminal_status": item.get("status", "missing"),
                "oracle_verdict": oracle.get("verdict", "missing"),
                "actions": item.get("actions"),
                "wall_s": round(wall_ms / 1000, 3) if isinstance(wall_ms, (int, float)) else None,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "check_status": check.get("status"),
                "policy_action": check.get("policy_action"),
                "patch_bytes": item.get("patch_bytes"),
                "packet_initial_sha256": item.get("packet_initial_sha256", ""),
            })
    return rows, mismatches

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.runs.is_dir():
        parser.error(f"runs directory does not exist: {args.runs}")
    rows, mismatches = collect(args.runs)
    if not rows:
        parser.error(f"no case bundles found in {args.runs}")
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / "task1_summary.csv"
    with dest.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Task 1 case summary", "",
        "Generated from saved logs only: no model calls and no fabricated outcomes.", "",
        "| Case | Origin | Arm | Live | Model | Oracle | Actions | Wall (s) |",
        "|---|---|---|---|---|---|---:|---:|",
    ]
    for row in rows:
        origin = row["change_origin"]
        if row["note_origin"] != "historical_document":
            origin += " / constructed note"
        lines.append(
            "| {case_id} | {origin} | {arm} | {is_live} | {model} | {oracle_verdict} | {actions} | {wall_s} |".format(
                origin=origin, **row
            )
        )
    genuine_ids = {
        r["case_id"] for r in rows
        if r["change_origin"] == "natural_commit" and r["note_origin"] == "historical_document"
    }
    pairs = {
        case for case in {r["case_id"] for r in rows}
        if len([r for r in rows if r["case_id"] == case and r["is_live"] and r["oracle_verdict"] != "missing"]) == 2
    }
    lines += [
        "",
        f"Observed live pairs: **{len(pairs)}** (cases with both arms recorded).",
        f"Cases with natural code change AND historical note: **{len(genuine_ids)}**.",
        f"Initial packet hash mismatches: **{len(mismatches)}** ({', '.join(mismatches) or 'none'}).",
        "",
        "Constructed fixtures, researcher-authored notes and fake backend runs are *not* historical",
        "incidents of documentation staleness. Case selection is explanatory, not prevalence estimation.",
        "A patch failure does not by itself establish the agent relied on a stale claim.",
        "",
    ]
    (args.out / "task1_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {dest} and {args.out / 'task1_summary.md'}")
    if mismatches:
        raise SystemExit("WARNING: blind/checked starting packet SHA mismatch")

if __name__ == "__main__":
    main()
