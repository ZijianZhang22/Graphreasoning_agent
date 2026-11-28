# DocAgent Task 2 — RunPod execution and formal grading

This is a **wrapper** for Xiangrui's existing `experiments/paired_runs/` implementation; it is not a new competing benchmark. All three arms, memory generation, checker and patch grader remain upstream.

## Exact study design

- **One disjoint development pilot** × 3 arms; **four held-out issues** × 3 arms: **15 real Agent sessions** if the full tier is feasible.
- Each issue: `source_only`, `static_stale`, `selective_stale`.
- SWE-bench Lite `test` split and the pinned revisions in `study.task2.json`.
- No fake or smoke outcomes count as live observations. The final grade is **official SWE-bench resolution**, not a local apply-check.
- The dataset revision comes from upstream's example and **may no longer match the revision served by Hugging Face**. The upstream loader intentionally stops if there is a mismatch. Re-pin deliberately before preparing; do not change after freezing the manifest.
- `--screen.max_candidates=40`, timebox 60 minutes: an **attempt** to find five eligible issues, not a guarantee. If the cohort cannot fill, choose a smaller **complete** tier before seeing held-out results.

## Setup: important distinction between solving and grading

A RunPod GPU runs the **Agent**. Official SWE-bench **grading** additionally needs a separate Docker-capable Linux environment, often 8 CPU cores / 120 GiB free disk. `ubuntu-latest` GitHub Actions runners may lack sufficient space or CPU; a workflow being installed does not prove grading works.

For GitHub Actions, use a **writable fork of Xiangrui's `DocAgent`**, with `.github/workflows/swebench-grade.yml` committed and Actions permissions enabled. An upstream `xiangruiSun/DocAgent` origin is not writable by a regular collaborator. The separate `Graphreasoning_agent` repository is a convenient home for our wrapper, but it **does not itself contain the upstream SWE-bench grader workflow**. Credentials for `git push` must be configured in RunPod; do not store tokens in repository files.

If the GitHub runner cannot grade, export grading request folders to a separate Docker host and run `experiments/grader/remote_grade.py` there; copy the resulting `done.json`, `outcome.json`, and harness reports back into the exact `.grader_store/results/<request_id>` path. Do not mistake an empty or infrastructure-error `done.json` for successful grading.

## RunPod setup

On a persistent `/workspace` volume, with your *writable fork* checked out at `/workspace/docagent-task1/DocAgent` and this wrapper folder present (for example within `Graphreasoning_agent/docagent_task2_runpod`):

```bash
cd /workspace/docagent-task1/DocAgent
git rev-parse HEAD
# Check origin points to YOUR writable DocAgent fork if using GitHub Actions:
git remote -v

ollama serve  # only if service is not already running; use a separate terminal
ollama pull qwen3-coder:30b

cd /workspace/Graphreasoning_agent/docagent_task2_runpod
python3 -m unittest -v test_run_task2.py
python3 run_task2.py preflight
python3 run_task2.py smoke
```

**Do not just use `git pull` on an old DocAgent checkout and mix versions**. Record upstream SHA and driver changes before freezing. Set `DOCAGENT_UPSTREAM_DIR=/your/DocAgent/path` if different.

## Staged run: preferred for auditable recovery

```bash
cd /workspace/Graphreasoning_agent/docagent_task2_runpod
python3 run_task2.py prepare

# Produce official base/gold controls for ALL selected issues, before any paid solves.
# With a writable fork + a working Actions grader:
python3 run_task2.py controls --route github_actions --push --wait-s 0
# If pending, check Actions and repeat this same command to retrieve completed results.

python3 run_task2.py pilot
python3 run_task2.py grade-pilot --route github_actions --push --wait-s 0
# Wait for a VERIFIED official pilot result before running held-outs.

# Human relevance annotation: use relevance.review_template.json; write a clean
# JSON object with per-issue {"claim_ids": [...], "paths": [...]} at
# /workspace/docagent-task2/.grader_store/relevance.json
# Reviewers should not inspect reference patches.
python3 run_task2.py heldout
python3 run_task2.py grade-heldout --route github_actions --push --wait-s 0
python3 run_task2.py report
python3 run_task2.py status
python3 run_task2.py package
```

You may use `python3 run_task2.py all --route github_actions --push --wait-s 0` for orchestration **after the grader is configured and the human annotation is completed**. It intentionally stops at pending grading or missing annotations, and is safe to resume with the same output path. `--route local` is for a Linux host on which the official Docker harness is available; a RunPod pod does **not** automatically provide nested Docker.

## Guardrails and evidence

- Before the solver, the **unmodified base must fail an official FAIL_TO_PASS test and the reference patch must resolve**. Otherwise the wrapper blocks solving.
- Pilot needs three **live sessions** and at least one nonempty diff. A fake-only run does not qualify.
- The held-out tier is frozen before looking at results; the wrapper refuses to silently accept a partial four-Issue cohort.
- Relevant claims/paths require independent annotation; automatic matching of words in the issue is **only a candidate screening proxy**.
- A real official outcome is only `resolved` if the grader reports it. Resource and token counts are retained from upstream where exposed. Missing values stay missing, not zero.
- The package includes source issue statements, claim lists, patches, compact traces, frozen manifest and grading reports; excludes snapshot tar caches and hidden evaluator-only dataset files. `TASK2_RISK_AUDIT.md` lists remaining upstream limitations.

The wrapper uses the upstream agent limits of 360 seconds and 12 total visible tool/check actions per arm. The planner uses at most two actions, with a 600-byte handoff. The checker verifies up to three suspect claims. Configuration changes after the frozen manifest mean a new study block, not silently merged comparisons.