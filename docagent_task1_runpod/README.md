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
