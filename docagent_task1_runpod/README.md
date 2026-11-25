# DocAgent Task 1: RunPod + Qwen3:8B

This folder is a **standalone RunPod launcher and reporting layer** for Task 1
(staleness case studies) from [xiangruiSun/DocAgent](https://github.com/xiangruiSun/DocAgent).
It does **not** replace or rewrite the upstream experiment runner. It clones the
exact, known-to-contain-Task-1 commit `d44ab1bb365fb7c151577dbd321a52fbf06d38ae`.

It runs one local model, `qwen3:8b` through Ollama, using the upstream
`experiments/backends/toolloop_agent.py` with five observable tools:
`list_dir`, `read_file`, `search`, `replace_in_file`, and `finish`.

## RunPod quick start

Deploy a **GPU Pod**, not a serverless inference endpoint. A Linux/PyTorch image
with Python 3.10+, Git, curl, 30–50 GB available storage, and preferably >=16 GB
VRAM is a comfortable starting point. GPU size is an engineering suggestion,
not a scientific requirement. Open a RunPod terminal:

```bash
cd /workspace
git clone --branch feature/docagent-task1-runpod-qwen3-8b \
  https://github.com/ZijianZhang22/Graphreasoning_agent.git
cd Graphreasoning_agent/docagent_task1_runpod

bash launch.sh setup    # install/start Ollama, pull qwen3:8b, clone pinned DocAgent
bash launch.sh smoke    # fake backend; verifies wiring but is NOT an agent result
bash launch.sh demo     # Qwen3:8b, both arms, constructed C00 example
bash launch.sh report demo
```

Setup only downloads the model once on persistent storage. To inspect the Pod:
`bash launch.sh status`. If `/workspace` is unavailable, set
`DOCAGENT_WORKDIR` to a writable directory before running setup.

**Never count the demo as one of the four natural case studies.** It uses the
upstream `C00` synthetic fixture to test model/tool integration.

## Run genuine cases

1. Read the upstream [Task 1 requirements](https://github.com/xiangruiSun/DocAgent/blob/main/docs/requirements/Task_1_Case_Studies.md).
2. Create a `cases.json` from the example in
   `/workspace/docagent-task1/DocAgent/experiments/case_studies/cases.example.json`.
   Replace the sample with at least **four separately verified cases**. Record
   real repository URL, exact old `s` / new `t` commit hashes, supported old
   claim, changed path/symbol, category, provenance, neutral task, and oracle.
   Keep evaluator-only answers in `cases.evaluator.json` beside the manifest.
   For patches, oracle commands must be executable against the clean `t`
   snapshot and must not reveal hidden solutions to the model.
3. Validate before spending GPU time and run one case, then repeat:

```bash
bash launch.sh validate /workspace/my_cases/cases.json
bash launch.sh run /workspace/my_cases/cases.json C01
bash launch.sh run /workspace/my_cases/cases.json C02
bash launch.sh run /workspace/my_cases/cases.json C03
bash launch.sh run /workspace/my_cases/cases.json C04
bash launch.sh report real
```

The `run` command executes **blind** and **checked** on the same fixed
`qwen3:8b` backend with defaults of 180 seconds / 8 visible actions per arm.
The checked arm's claim check is a *separate experimental verifier*; DocAgent's
released helper supplies only the file-level change signal.

Results are under `/workspace/docagent-task1/runs/real/`:
- `<case>/case.json` — provenance and source evidence at `s`, `t`.
- `<case>/attempts/<attempt>/ledger.jsonl` — observed tools and checks.
- `<case>/attempts/<attempt>/patch.diff`, `summary.json` — generated patch, oracle result, token/time counts when available.
- `reports/` — upstream per-case reports.
- `summary/task1_summary.csv` and `task1_summary.md` — compact tables for slides (generated offline).

## Reproducibility and limitations

- Compare only runs using the same model, quantization, prompt, tools, context
  placement and budgets. Record Ollama version, GPU and actual memory use
  separately if available. Do not mix a Qwen3 8B arm with Qwen3 14B.
- The upstream case driver supports `signature_has_param`,
  `symbol_owner`, and `literal_equals` predicate checks. It does not prove
  arbitrary program behavior; use a task-specific executable oracle.
- `qwen3:8b` may fail tool calls or edits. Those are genuine observations,
  but separate backend incompatibility from documentation-reliance failures.
  Test the synthetic demo before committing to four natural cases.
- **Task 1 does not need SWE-bench Docker**. It does need internet to fetch Git
  histories for real cases, and enough CPU/GPU/RAM for the selected model.
- Case collection is selective: case frequencies do not estimate general
  repository staleness rates. Fake/demo sessions do not count as live evidence.
- Scripts do not create API keys, request grader solutions, or modify the
  original `Graphreasoning_agent` project. Logs and models remain on RunPod
  unless you back them up. Stop the GPU Pod when finished.

The original graph-reasoning experiment at the repository root is unchanged.


## Four prepared real-history cases (C01–C04)

This branch now includes `cases.json`, `cases.evaluator.json`,
`CASE_EVIDENCE.md`, and `verify_case_evidence.py`.
These are **real source-history changes**, with *researcher-authored notes*.
They are **not** real-model results or proven historical documentation incidents.
Details and source links: [CASE_EVIDENCE.md](CASE_EVIDENCE.md).

After the RunPod setup and synthetic demo:

```bash
bash launch.sh validate "$PWD/cases.json"
python3 verify_case_evidence.py --cache /workspace/docagent-task1/cache
for id in C01 C02 C03 C04; do
  bash launch.sh run "$PWD/cases.json" "$id"
done
bash launch.sh report real
```

- **C01:** Werkzeug moved `_dump_date` to `werkzeug/http.py`.
- **C02:** urllib3 removed `Retry(method_whitelist=...)`.
- **C03:** itsdangerous moved `tests/test_serializer.py` into a test package.
- **C04:** sampleproject removed only trailing blank lines; `add_one` stayed correct.

The historical Git sources have been inspected; **RunPod cloning, end-to-end
validation and Qwen3:8B model inference have not yet been executed**.
Each case requests independent human review (`status: pending`) before a
research report claims verified behavior. C03 currently evaluates a
localization answer; it does not execute pytest collection.


## One command to run all four cases and export a ZIP

After cloning this branch on a RunPod **GPU Pod**, run from this folder:

```bash
bash run_all.sh
```

This automatically performs: Ollama/Qwen3:8B setup, fake-backend smoke
check, source manifest validation, independent Git-history evidence audit,
a separate synthetic C00 integration demo, four C01–C04 real-model case
runs (blind and checked in each), reports/CSV generation, and ZIP export.

**The ZIP path is printed as `RESULT ZIP:` at the end**, normally
`/workspace/docagent-task1/exports/DocAgent_Task1_<batch>.zip`.
Download it through the RunPod file browser. Every invocation has an
independent batch directory and does not overwrite previous experiments.

For an already provisioned Pod where Ollama, Qwen3:8B and DocAgent
have been installed:

```bash
SKIP_SETUP=1 SKIP_DEMO=1 bash run_all.sh
```

The package contains inputs, old/current claim evidence, model identity,
initial and checked memory packets, raw action logs, generated patches,
oracle verdicts, reports, per-case CSV, Git revision metadata, and
stage-specific logs. It omits cloned Git source repositories, model
weights, caches and secrets.

If a case fails, the remaining cases are still attempted and the
archive records any missing or incomplete sessions. If setup, smoke
or source validation fails, no live case runs start, but diagnostic
logs are still packaged. A finished shell command does **not**
guarantee a model solved the task: inspect `batch_status.json` and each
arm's `oracle_verdict`. C03 uses a localization oracle rather than
executing the complete historical pytest suite.

The script does not automatically push experimental outputs to GitHub.


## Replicate Xiangrui Task 1 three times (24 live sessions)

This is a **separate, opt-in study extension**, not a change to Xiangrui's
original four-case Task 1 specification. The four original cases, claims,
task prompts, oracles and case driver are kept **unchanged**.

On an existing RunPod with Ollama and the pinned DocAgent installed, run:

```bash
cd /workspace/Graphreasoning_agent
git pull
cd docagent_task1_runpod
python3 test_repeated.py
python3 run_repeated.py --skip-setup
```

For a fresh RunPod Pod, the last line becomes:

```bash
python3 run_repeated.py
```

Defaults: **3 rounds x 4 cases x 2 arms = 24 live sessions**. Within each
round, Blind and Checked share the same predetermined Qwen3:8B/Ollama seed;
across rounds the seeds are 20261119, 20261120, 20261121. Temperature stays
at 0; contexts, tasks, tool budgets and source revisions are frozen. Both
arms begin on clean independent source snapshots. Do **not** interpret three
temperature-zero repeats as independent statistical samples.

The script creates a **unique** batch for each invocation, with full
per-round case reports and raw session traces:

```text
/workspace/docagent-task1/repeat_batches/<batch>/analysis/stability.md
/workspace/docagent-task1/repeat_batches/<batch>/analysis/stability.json
/workspace/docagent-task1/repeat_batches/<batch>/analysis/sessions.csv
/workspace/docagent-task1/repeat_batches/<batch>/analysis/pairs.csv
/workspace/docagent-task1/exports/DocAgent_Task1_Repeated_<batch>.zip
```

The ZIP contains the input manifests, per-attempt logs and patches,
per-round reports, model backend configuration, stability summaries, failure
logs and integrity hashes. A missing or non-live arm is explicitly counted
as incomplete. The shell may return a nonzero code if a case fails; the
script still attempts to write its partial ZIP.

### Optional 2 historical-document-derived candidates (separate track)

Two additional cases have been curated and documented in
[EXTRA_CASE_EVIDENCE.md](EXTRA_CASE_EVIDENCE.md):

- C05: Flask deprecated send_file argument removed, with actual historical
  changelog and source docstring evidence.
- C06: Requests adds type annotations while preserving the documented
  request dispatch function.

They have natural upstream code changes and contemporary human documentation.
However, the compact **memory notes were extracted/paraphrased by the
researcher**, so their note provenance is `snapshot_generated`, **not**
an untouched historical document. Independent reviewer labels remain pending.

To include them in the same **3-round experiment but a separate analysis
track**, use:

```bash
python3 run_repeated.py --skip-setup --extra
```

That executes **24 primary + 12 optional = 36** intended live sessions,
not 36 interchangeable primary Task 1 observations. Results are separately
reported as `primary` and `extra`; never pool their pass rates.

Run `python3 test_repeated.py` first for an offline accounting smoke test.
The old `bash run_all.sh` remains available for the original one-round
8-session experiment.


## Task 1 acceptance evidence supplement (no GPU rerun)

Xiangrui's original requirement asks for independent *behavioral* evidence
around C02's removed API keyword, actual pytest selector collection / exit
codes / node IDs for C03, and independent review of all four source facts.
The source bundles and 24 original agent runs remain unchanged.

The supplemental auditor uses **already cached Git source snapshots** on
RunPod. It executes Python imports and pytest collection against pinned s/t,
checks ownership in C01, and confirms unchanged executable AST in C04. It
also retries the released DocAgent **unmodified** `diff_since` and
`match_any` functions from a shared-object Git worktree, because the
original `cases.py` gate made a temporary local clone whose history can
exclude old commits. This is an *additional diagnostic*, not a retroactive
replacement for the original failed gate logs. Missing dependencies are
reported as incomplete checks, not as successful behavior evidence.

From your existing RunPod, run:

```bash
cd /workspace/Graphreasoning_agent
git pull
cd docagent_task1_runpod
python3 -m py_compile audit_task1_evidence.py

python3 audit_task1_evidence.py \
  --runs /workspace/docagent-task1/repeat_batches/20261125T213451Z-5947/runs/primary/round_01
```

The command prints paths to `audit_summary.json` and one ZIP under
`/workspace/docagent-task1/acceptance_audits/`.

**Note on test dependencies:** If C03 reports `No module named pytest`,
install pytest in the Pod's Python environment and rerun only the audit:
`python3 -m pip install pytest`. Old dependencies may be incompatible with
the Pod's Python; preserve the exact error and do not report a passing test
collection in that case. The supplemental audit does not run pytest test
bodies, only real `--collect-only` selections as required for evidence.

Check `C02_api_behavior.json` for actual API acceptance and exceptions,
`C03_pytest_collection.json` for exit codes, counts and selector node IDs,
and `C01_gate.json` through `C04_gate.json` for exact released-helper
file-level changes. The new `replayed/*.md` are rebuilt offline with no
model invocation. The principal original data is still the earlier ZIP.

**Human sign-off is not automated.** Have a second researcher independently
complete [TASK1_REVIEW_TEMPLATE.md](TASK1_REVIEW_TEMPLATE.md), recording
their own s/t labels before seeing the pre-existing decisions. The four
`human_review` fields remain pending until that work is genuinely done.
