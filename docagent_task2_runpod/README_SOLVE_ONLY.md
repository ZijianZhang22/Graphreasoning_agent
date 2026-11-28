# New RunPod: solve-only Task 2 workflow (official grading deferred)

RunPod only performs data preparation, three-arm real Agent inference, and patch/trace capture. A later independent Docker host or GitHub Actions grades the saved requests. **This intentionally deviates from Xiangrui's Task 2 protocol requiring official base/gold controls before held-out solving.** Do not call any `resolved` status until the official grader completes. Record this limitation in the report; if strict acceptance is required, grade the controls before the solver.

1. In RunPod console, create one GPU Pod (suggest L40S 48GB), official PyTorch template, persistent /workspace volume (100 GB minimum, ideally 150 GB for model & Git caches), connect via Web Terminal. Container root disk can be 30-50 GB; the persistent volume must hold all artifacts.
2. Clone the existing Graphreasoning_agent repository from GitHub; all these scripts are already included in `docagent_task2_runpod/`. No ZIP upload is necessary.
3. In the Pod's terminal:

```bash
cd /workspace
 git clone -b feature/docagent-task1-runpod-qwen3-8b https://github.com/ZijianZhang22/Graphreasoning_agent.git
 cd /workspace/Graphreasoning_agent/docagent_task2_runpod
bash deploy_new_runpod.sh
python3 solve_only_task2.py preflight
python3 solve_only_task2.py smoke
python3 pin_dataset_current.py
# If the printed revision differs, explicitly rerun with --write BEFORE prepare.
python3 pin_dataset_current.py --write
python3 solve_only_task2.py prepare
```

4. Examine `screening_log.json` and `relevance.review_template.json` at `/workspace/docagent-task2/`. If the fixed 4-issue tier was not found, preserve logs and create a new study with a smaller complete tier **before seeing solver results**. Do not edit a frozen study's manifest in place.
5. To compute patches and traces:

```bash
cd /workspace/Graphreasoning_agent/docagent_task2_runpod
python3 solve_only_task2.py pilot
python3 solve_only_task2.py heldout
python3 solve_only_task2.py export
python3 solve_only_task2.py status
ls -lh /workspace/docagent-task2_submission.zip
```

6. Download `/workspace/docagent-task2_submission.zip` **and** retain all important raw artifacts if you need offline report regeneration after moving storage; do not terminate the Pod before confirming both backup and ZIP integrity.
7. For formal grade later: extract the ZIP on a compatible machine with a pinned DocAgent checkout; for each `grading_requests/<request-id>/request.json`, use `experiments/grader/remote_grade.py --request <...>/request.json --out <...>/results/<request-id>` in a Linux Docker environment, then check `done.json` `setup_error`, `outcome.json` and official test statuses. This requires official SWE-bench dependencies and dataset access; a fake or static diff check cannot score an issue.

The ZIP contains predictions and separate official base/reference control requests, but **does not contain hidden gold/test patches**. The grader gets these from the pinned public benchmark dataset in an isolated grader environment. No GPU is required to grade if the Docker host has enough CPU/RAM/disk.

Use no public Ollama port; it listens on `127.0.0.1:11434` inside the Pod only. Use a persistent disk and export before Stop/Terminate.