# DocAgent Task 2 — RunPod setup

This directory contains frozen starter configs for Xiangrui's existing
`experiments/paired_runs/` implementation:

- `study.task2.json`: SWE-bench Lite pinned example, one independent pilot
  plus **four held-out issues** (3 arms each; 15 live sessions including pilot).
- `backend.qwen3-coder-30b.json`: local Ollama model and reproducibility settings.

**Full guarded runner and local offline tests** are available in the companion
`DocAgent_Task2_RunPod_Starter.zip` delivered in this conversation:
`run_task2.py`, `test_run_task2.py`, `README_RUNPOD.md`, and
`TASK2_RISK_AUDIT.md`. Place those files in this directory on the Pod.
The configs in the ZIP match the configs here.

The upstream repository already contains the memory builder, checker,
`source_only`/`static_stale`/`selective_stale` solver, real Ollama backend,
official grading request generator, and offline report generator. This is
a deployment wrapper, not a replacement experimental implementation.

## Starting order

1. Checkout a writable fork of `xiangruiSun/DocAgent` (with the grading
   workflow) at `/workspace/docagent-task1/DocAgent`. Record its SHA.
2. Ensure Ollama is running and `ollama pull qwen3-coder:30b` completed.
3. `python3 -m unittest -v test_run_task2.py`
4. `python3 run_task2.py preflight`
5. `python3 run_task2.py smoke`
6. `python3 run_task2.py prepare`
7. Official base/gold controls **before** agent solves.
8. Pilot (3 live attempts), official pilot grading, independent relevance
   annotation, held-out cohort (12 attempts), official grades, report, package.

For remote grading, use `--route github_actions --push`, but only after
verifying that the fork's Actions runner can run the SWE-bench Docker harness.
GitHub-hosted runners may have insufficient disk for official grading.
No code or successful result has been fabricated; the live experiment remains
unexecuted until the user runs the Pod.

Original Task 2 brief:
https://github.com/xiangruiSun/DocAgent/blob/main/docs/requirements/Task_2_Experimental_Runs.md
