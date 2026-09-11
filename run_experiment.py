#!/usr/bin/env python3
import argparse, json, time
from pathlib import Path
import pandas as pd

from graph_agent.llm import LLM
from graph_agent.benchmark import load_examples
from graph_agent.agent import AdaptiveGraphAgent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nlgraph-root", required=True)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--num-examples", type=int, default=100)
    ap.add_argument("--task", choices=["connectivity", "shortest_path"], default="shortest_path")
    ap.add_argument("--difficulty", choices=["easy", "hard"], default="hard")
    ap.add_argument("--mode", choices=["taxonomy", "no_taxonomy"], default="taxonomy")
    ap.add_argument("--run-root", default="runs")
    args = ap.parse_args()

    run_dir = Path(args.run_root) / f"{args.task}-{args.difficulty}-{args.mode}-{time.strftime('%Y%m%d-%H%M%S')}"
    examples = load_examples(
        args.nlgraph_root,
        difficulty=args.difficulty,
        limit=args.num_examples,
        task=args.task,
    )
    agent = AdaptiveGraphAgent(
        LLM(args.model),
        run_dir,
        use_taxonomy=(args.mode == "taxonomy"),
    )

    rows = []
    for i, ex in enumerate(examples, 1):
        row = agent.run_one(ex)
        row["index"] = i
        rows.append(row)
        print(
            f"[{i}/{len(examples)}] task={row['task']} first={row['first_try_ok']} "
            f"final={row['final_ok']} failure={row['first_failure']} "
            f"second={row['used_second_solver']} critic={row['used_critic']}"
        )

    df = pd.DataFrame(rows)
    u = agent.metrics.usage
    summary = {
        "mode": args.mode,
        "task": args.task,
        "difficulty": args.difficulty,
        "num_examples": len(df),
        "accuracy": float(df.final_ok.mean()) if len(df) else 0.0,
        "first_try_accuracy": float(df.first_try_ok.mean()) if len(df) else 0.0,
        "avg_calls_per_example": u.calls / max(1, len(df)),
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "latency_s": u.latency_s,
        "repairs": agent.metrics.repairs,
        "critics": agent.metrics.critics,
        "failure_counts": df["first_failure"].dropna().value_counts().to_dict() if len(df) else {},
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(run_dir / "results.csv", index=False)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\nSUMMARY")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
