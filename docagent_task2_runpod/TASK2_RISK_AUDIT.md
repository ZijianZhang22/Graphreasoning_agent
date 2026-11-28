# Task 2 code review: what Xiangrui has implemented and what still needs testing

Reviewed `xiangruiSun/DocAgent` repository's current `docs/requirements/Task_2_Experimental_Runs.md`, `experiments/paired_runs/` modules, backend, and grader workflow, 2026-11-28. This is **source inspection**, not evidence that real SWE-bench runs have succeeded.

## Module-level readiness

| Subsystem | Found upstream | What it does | Caveats |
|---|---|---|---|
| Dataset pin + selection | `prlib/dataset.py`, `prepare.py` | Seeded round-robin over pytest/Sphinx/SymPy Lite, picks `t` and `s` older by ≥30 days, exports restricted snapshots and screening log. | Dataset loader requires pinned revision = currently served revision unless cached; full bare repo clones are expensive. Selection rule is narrow and a four-issue tier is not guaranteed. |
| Memory generation | `prlib/memory.py` | AST extraction of Python signatures and literal module defaults at old `s`; bounded Markdown documents; calls released `context_bundle` router. | Excludes tests/documentation, dynamic defaults, symbol location and many kinds of facts. Generated memory may miss the relevant cause. |
| Selective checker | `prlib/checker.py` | Verifies at most three claims from stale routed docs, reuses supported, repairs unique signatures/literals, otherwise omits. | First suspects in retrieval order, not necessarily the most issue-relevant. Claim repair is not runtime semantic validation. |
| Three-arm solver | `prlib/runner.py`, `backends/toolloop_agent.py` | Clean snapshot, fresh read-only planner and implementer, time/action budgets, isolated tool loop, patch capture and local apply-check. | Model quality unknown; limited file-edit tools; local apply-check is NOT official resolution. |
| Official grader | `prlib/grading.py`, `grader/remote_grade.py`, `.github/workflows/swebench-grade.yml` | Base and reference controls; produces official prediction JSONL; harness runs locally or via GitHub Actions branch and imports results. | Runner storage/Docker, network and write permissions must be verified. `done.json` may exist with `setup_error`; do not mark it graded successfully. |
| Report | `prlib/report.py` | Offline per-issue CSV/Markdown/JSON; paired success, resource/usage metrics, memory checks and exploration proxies. | Relevance annotations start empty; `acted_upon` is explicitly marked for human trace review. No significance claim with 2–6 issues. |
| Integration | `validate_pipeline.py` | One-issue six-stage acceptance including two controls, three live attempts, grading, report. | Requires an explicit real Lite ID and a reachable grader; no evidence this was run for the user's configuration. |
| Smoke tests | `bench.py smoke --backend fake` | Checks distinct arm paths, identical static/selective initial packets, no source-only generated packet and offline report. | Fake smoke is not a valid Agent solve; needs actual execution in the chosen checkout. |

## Specific concerns verified in code

1. `dataset.load_split` calls Hugging Face served revision and requires an exact match to the example pin; do not assume the pin is current. Dataset rows are loaded over the row API, **not** necessarily a historical immutable path if the upstream current revision differs.
2. `prepare.py` accepts candidates only if a *contradicted*, *issue-mentioned* and *routed/exposed* claim exists. It logs router misses. Expanding the screen budget can be necessary to fill a cohort; it does not justify cherry-picking based on success outcomes.
3. `memory.build_claims` extracts two narrow AST predicate types; it cannot represent all realistic API/behavior drift. Make this limitation explicit in the final report.
4. `checker.selective_packet` takes the first suspect claim IDs from stale routed documents up to the cap; the target claim may remain unexamined. Report which claims actually got checked.
5. `runner.run_attempt` uses a six-minute shared allowance and saves planner/implementer events, packet hashes, tool counts, token counts when exposed, patch and independent apply check. It can produce a patch even if official evaluation fails.
6. `grading.read_outcome` and `control_verdict` separate `pending`, `infra_error`, `unresolved`, `resolved`. However the outer CLI can print `graded` when a grading result directory contains a `done.json` with `setup_error`; our wrapper explicitly blocks that for base/gold controls.
7. The Actions workflow uses standard `ubuntu-latest` and builds a Docker image via official harness. The hardware/storage may be inadequate; test a *real* control request before committing large GPU time. Hosted runners may not meet the 120GiB published SWE-bench recommendation.
8. Report `RQ1` relevance requires `relevance.json` annotations; otherwise there is no verified first-relevant-source metric. Trace-supported claim reliance / mistaken edits still require human review.
9. No `fresh`, `rebuild`, or released review-and-sync experimental arms are implemented for primary Task 2; they are optional expansion, and the report explicitly lists them as not measured.
10. The user's Task 1 RunPod folder is only a previous case-study wrapper. Its Task 1 oracle and 24-session traces must not be used as held-out Task 2 SWE-bench resolutions.

## Next evidence milestones

- Pass offline `bench.py smoke --backend fake` in the user's new checkout.
- Verify dataset pin resolution, at least one Pilot and 4 held-out candidate snapshots, exact model/tool use and strict memory-policy boundaries.
- Pass official base + gold controls for every selected issue.
- Obtain all three **live** Pilot traces with at least one usable diff, official Pilot grades.
- Freeze human claim/path relevance labels before interpreting held-out exploration.
- Obtain complete 12 held-out live attempts and official grades; report missing data separately.
- Verify generated report can be regenerated with no model calls and package without hidden gold patches or credentials.
