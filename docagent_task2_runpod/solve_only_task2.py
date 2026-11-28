#!/usr/bin/env python3
"""Deferred-grading launcher for DocAgent Task 2.

Run only the real solver on a GPU Pod. Prepare official control/prediction
requests without submitting them. Scientific limitation: official base/gold
controls have NOT been checked before solving, as demanded by the Task 2
protocol. Every output remains UNGRADED until controls + official harness pass.

Do not use fake/smoke results as evidence, do not relabel ungraded as resolved.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

import run_task2 as base

ARMS = base.ARMS


def record(out: Path, detail: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "DEFERRED_GRADING_STATUS.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps({**old, **detail}, indent=2, ensure_ascii=False) + "\n")


def group_checks(args, group: str) -> tuple[list[str], list[str]]:
    m, _ = base.frozen(args.out)
    pilot = [x["instance_id"] for x in m["issues"] if x["status"] == "pilot"]
    held = [x["instance_id"] for x in m["issues"] if x["status"] == "held_out"]
    expected = int(json.loads((args.out / "study.frozen_input.json").read_text())["tier"]["held_out"])
    if len(pilot) != 1 or len(held) != expected:
        raise base.Blocked(f"Prepared incomplete cohort: {len(pilot)} pilot and {len(held)}/{expected} held-out. Preserve screening_log.json; reduce tier before inspecting outcomes.")
    return pilot, held


def completed(args, ids: list[str]) -> dict:
    details = {}
    for iid in ids:
        details[iid] = {}
        for arm in ARMS:
            attempts = sorted((args.out / "runs" / iid / arm).glob("*/summary.json"))
            if not attempts:
                raise base.Blocked(f"MISSING real solver attempt: {iid}/{arm}")
            row = json.loads(attempts[0].read_text())
            if row.get("is_live") is not True:
                raise base.Blocked(f"NON-LIVE solver attempt: {iid}/{arm}: {row.get('status')}")
            details[iid][arm] = {
                "status": row.get("status"), "patch_bytes": row.get("patch", {}).get("bytes"),
                "attempt_id": row.get("attempt_id"), "is_live": True,
            }
    return details


def make_requests(args, ids: list[str]) -> None:
    for iid in ids:
        for controls in (True, False):
            flags = ["grade", "--manifest", str(args.out / "prepared/frozen.json"),
                     "--instance-id", iid, "--workers", "1", "--route", "github_actions"]
            if controls:
                flags.append("--controls")
            # No --push: writes the official request/predictions, never starts Docker.
            base.bench(args, *flags)


def run_phase(args, stage: str) -> None:
    base.preflight(args, require_model=True)
    pilot, held = group_checks(args, stage)
    if stage == "pilot":
        base.bench(args, "pilot", "--config", str(args.out / "study.frozen_input.json"),
                   "--backend", str(args.backend), "--out", str(args.out / "prepared"))
        d = completed(args, pilot)
        if not any(v["patch_bytes"] and v["patch_bytes"] > 0 for v in d[pilot[0]].values()):
            raise base.Blocked("Pilot completed but produced no nonempty patch. Freeze status and diagnose before held-out trials.")
    else:
        completed(args, pilot)  # don't start held-out before pilot live completion
        base.bench(args, "run", "--manifest", str(args.out / "prepared/frozen.json"),
                   "--backend", str(args.backend), "--resume", "--batch")
        d = completed(args, held)
    record(args.out, {
        "status": "SOLVER_FINISHED_UNGRADED", "stage_last_completed": stage,
        "official_controls_verified": False, "official_patch_scores_available": False,
        "protocol_deviation": "Deferred official base/gold controls; Task 2 normally requires controls before solver; preserve this limitation in the final report.",
        "attempts": d,
    })
    print("SUCCESS: real solver sessions saved; NO official resolution grades have been computed.", flush=True)


def export(args) -> None:
    pilot, held = group_checks(args, "export")
    all_ids = pilot + held
    d = completed(args, all_ids)
    make_requests(args, all_ids)
    base.report(args)  # offline; labels official outcomes as ungraded
    record(args.out, {
        "status": "SOLVER_FINISHED_UNGRADED", "official_controls_verified": False,
        "official_patch_scores_available": False,
        "ready_for_future_official_grading": True,
        "issues": d,
        "what_to_do_later": "Run official base/gold controls and prediction grading on a compatible Docker Linux host; import harness outcomes and rerun offline report. Do not claim resolved yet.",
    })
    base.package(args)
    archive = args.out.parent / f"{args.out.name}_submission.zip"
    with zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as z:
        for name in ("DEFERRED_GRADING_STATUS.json", "relevance.review_template.json"):
            path = args.out / name
            if path.is_file():
                z.write(path, name)
        p = args.out / ".grader_store" / "relevance.json"
        if p.is_file():
            z.write(p, "reviewed_relevance.json")
        z.write(args.backend, "backend.config.redacted.json")
        z.writestr("READ_FIRST_UNGRADED.txt", "Real Qwen Agent patches are included. Official SWE-bench scores are not. Base/gold controls were intentionally deferred; this diverges from the Task 2 required experiment order. Report any such deviation and do not claim resolution before official grading.\n")
    with zipfile.ZipFile(archive) as z:
        bad = z.testzip()
        if bad:
            raise base.Blocked(f"Failed ZIP integrity test: {bad}")
    print("EXPORT:", archive, "SIZE:", archive.stat().st_size, "bytes", flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("preflight", "smoke", "prepare", "pilot", "heldout", "export", "status"))
    p.add_argument("--docagent", type=Path, default=base.DEFAULT_DOCAGENT)
    p.add_argument("--out", type=Path, default=base.DEFAULT_OUTPUT)
    p.add_argument("--study", type=Path, default=base.HERE / "study.task2.json")
    p.add_argument("--backend", type=Path, default=base.HERE / "backend.qwen3-coder-30b.json")
    args = p.parse_args()
    for key in ("docagent", "out", "study", "backend"):
        setattr(args, key, getattr(args, key).expanduser().resolve())
    args.route, args.push, args.wait_s = "github_actions", False, 0.0
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        if args.stage == "preflight":
            base.preflight(args, require_model=True)
        elif args.stage == "smoke":
            base.smoke(args)
        elif args.stage == "prepare":
            base.prepare(args)
            record(args.out, {
                "status": "PREPARED_CONTROLS_PENDING", "official_controls_verified": False,
                "protocol_deviation": "Deferred official controls if solver runs before grading.",
            })
        elif args.stage in ("pilot", "heldout"):
            run_phase(args, args.stage)
        elif args.stage == "export":
            export(args)
        elif args.stage == "status":
            base.status(args)
        return 0
    except base.Blocked as exc:
        print("BLOCKED:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
