#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import pandas as pd

from graph_agent.llm import LLM
from graph_agent.benchmark import load_examples
from graph_agent.duverg_agent import DuVerGLiteAgent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nlgraph-root", required=True)
    ap.add_argument("--model", default="openai/gpt-4o-mini")
    ap.add_argument("--num-examples", type=int, default=100)
    ap.add_argument("--task", choices=["connectivity", "shortest_path"], default="shortest_path")
    ap.add_argument("--difficulty", choices=["easy", "hard"], default="hard")
    ap.add_argument("--mode", choices=["duverg", "duverg_taxonomy"], default="duverg_taxonomy")
    ap.add_argument("--repair-budget", type=int, default=1)
    ap.add_argument("--run-root", default="runs")
    args = ap.parse_args()

    run_dir = Path(args.run_root) / (
        f"{args.task}-{args.difficulty}-{args.mode}-{time.strftime('%Y%m%d-%H%M%S')}"
    )

    examples = load_examples(
        args.nlgraph_root,
        difficulty=args.difficulty,
        limit=args.num_examples,
        task=args.task,
    )

    agent = DuVerGLiteAgent(
        LLM(args.model),
        run_dir,
        use_taxonomy=(args.mode == "duverg_taxonomy"),
        repair_budget=args.repair_budget,
    )

    rows = []
    for i, ex in enumerate(examples, 1):
        row = agent.run_one(ex)
        row["index"] = i
        rows.append(row)
        print(
            f"[{i}/{len(examples)}] "
            f"A={row['coder_a_ok']} B={row['coder_b_ok']} "
            f"agree={row['initial_agreement']} "
            f"resolution={row['resolution']} final={row['final_ok']}"
        )

    df = pd.DataFrame(rows)
    u = agent.metrics.usage

    summary = {
        "mode": args.mode,
        "task": args.task,
        "difficulty": args.difficulty,
        "num_examples": len(df),
        "accuracy": float(df.final_ok.mean()) if len(df) else 0.0,
        "coder_a_accuracy": float(df.coder_a_ok.mean()) if len(df) else 0.0,
        "coder_b_accuracy": float(df.coder_b_ok.mean()) if len(df) else 0.0,
        "both_initial_ok": float(df.both_initial_ok.mean()) if len(df) else 0.0,
        "initial_agreement_rate": float(df.initial_agreement.mean()) if len(df) else 0.0,
        "avg_calls_per_example": u.calls / max(1, len(df)),
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "latency_s": u.latency_s,
        "repairs": agent.metrics.repairs,
        "disagreements": agent.metrics.disagreements,
        "both_failed": agent.metrics.both_failed,
        "early_agreements": agent.metrics.early_agreements,
        "coder_a_failure_counts": df["coder_a_failure"].dropna().value_counts().to_dict() if len(df) else {},
        "coder_b_failure_counts": df["coder_b_failure"].dropna().value_counts().to_dict() if len(df) else {},
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(run_dir / "results.csv", index=False)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print("\nSUMMARY")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
