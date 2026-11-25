#!/usr/bin/env python3
"""Offline self-test for repeat aggregation and ZIP; no model, no network."""
from __future__ import annotations
import json
import tempfile
import zipfile
from pathlib import Path
import run_repeated as r


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory(prefix="task1-repeat-test-") as temp:
        batch = Path(temp) / "batch"
        # Simulate 4 primary cases x 3 rounds x 2 arms with matching hashes.
        for round_index in (1, 2, 3):
            for case in r.PRIMARY:
                for arm in ("blind", "checked"):
                    path = (batch / "runs" / "primary" / f"round_{round_index:02d}" /
                            case / "attempts" / f"{arm}-attempt" / "summary.json")
                    verdict = "pass" if (arm == "checked" or case == "C04") else "fail"
                    put(path, {
                        "arm": arm, "attempt_id": f"{case}-{arm}-{round_index}",
                        "is_live": True, "status": "completed",
                        "backend": {"model": "qwen3:8b"},
                        "oracle": {"verdict": verdict},
                        "packet_initial_sha256": "identical-" + case,
                        "finished_at": f"2026-11-25T21:0{round_index}:00Z",
                        "timing": {"wall_ms": 1000}
                    })
        result = r.report(batch, 3, False)
        assert result["overall"]["primary"]["live_sessions"] == 24
        assert result["overall"]["primary"]["matched_pairs"] == 12
        assert result["overall"]["primary"]["paired_outcomes"] == {
            "improved": 9, "both_pass": 3,
        }
        path = Path(temp) / "test.zip"
        r.archive(batch, path)
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            assert any(x.endswith("analysis/stability.json") for x in z.namelist())
            assert any(x.endswith("summary.json") for x in z.namelist())
        # Delete one arm: it must NOT be silently counted as a successful pair.
        damaged = (batch / "runs" / "primary" / "round_03" / "C01" /
                   "attempts" / "checked-attempt" / "summary.json")
        damaged.unlink()
        result = r.report(batch, 3, False)
        assert result["overall"]["primary"]["live_sessions"] == 23
        assert result["overall"]["primary"]["matched_pairs"] == 11
        assert result["overall"]["primary"]["paired_outcomes"]["incomplete"] == 1
        print("PASS repeated summary: 24 sessions -> 23 on missing arm")
        print("PASS pairing integrity and ZIP integrity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
