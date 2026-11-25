#!/usr/bin/env bash
# Run all DocAgent Task 1 experiments on a RunPod GPU and package the results.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="${DOCAGENT_WORKDIR:-/workspace/docagent-task1}"
UPSTREAM_DIR="${DOCAGENT_UPSTREAM_DIR:-$WORKDIR/DocAgent}"
MODEL="${QWEN_MODEL:-qwen3:8b}"
ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
BATCH_DIR="${TASK1_BATCH_DIR:-$WORKDIR/batches/$ID}"
EXPORT_DIR="${TASK1_EXPORT_DIR:-$WORKDIR/exports}"
ZIP_PATH="$EXPORT_DIR/DocAgent_Task1_$ID.zip"
LOG_DIR="$BATCH_DIR/logs"
MANIFEST="$HERE/cases.json"
export DOCAGENT_RUNS_DIR="$BATCH_DIR/runs"

mkdir -p "$LOG_DIR" "$EXPORT_DIR"
printf 'stage\texit_code\n' > "$BATCH_DIR/stage_status.tsv"
printf 'batch_id=%s\nmodel=%s\nworkdir=%s\n' "$ID" "$MODEL" "$WORKDIR" > "$BATCH_DIR/run_info.txt"

on_exit() {
  local exitcode="$1"
  trap - EXIT
  echo
  echo "Packaging all available results (including partial failures)..."
  if python3 "$HERE/package_results.py" \
    --batch "$BATCH_DIR" --sources "$HERE" \
    --upstream "$UPSTREAM_DIR" --model "$MODEL" --out "$ZIP_PATH"; then
    echo "RESULT ZIP: $ZIP_PATH"
    echo "Download it from the RunPod file browser or copy it from the Pod."
  else
    echo "ERROR: ZIP creation failed. Raw results remain at $BATCH_DIR" >&2
    exitcode=1
  fi
  echo "Raw results: $BATCH_DIR"
  exit "$exitcode"
}
trap 'on_exit "$?"' EXIT

run_stage() {
  local tag="$1" rc=0
  shift
  echo
  echo "==================== $tag ===================="
  if "$@" 2>&1 | tee "$LOG_DIR/$tag.log"; then
    rc=0
  else
    rc="$?"
  fi
  printf '%s\t%s\n' "$tag" "$rc" >> "$BATCH_DIR/stage_status.tsv"
  echo "STAGE $tag: $([[ "$rc" -eq 0 ]] && echo OK || echo FAILED)"
  return "$rc"
}

echo "Task 1 batch: $ID"
echo "Model: $MODEL"
echo "Case pairs: C01 C02 C03 C04 (blind + checked)"
echo "ZIP target: $ZIP_PATH"
echo "Optional flags: SKIP_SETUP=1 or SKIP_DEMO=1"

if [[ "${SKIP_SETUP:-0}" == "1" ]]; then
  printf '00_setup\tskipped\n' >> "$BATCH_DIR/stage_status.tsv"
else
  if ! run_stage 00_setup bash "$HERE/launch.sh" setup; then
    echo "Setup failed; not starting live experiments." >&2
    exit 1
  fi
fi

if ! run_stage 01_smoke bash "$HERE/launch.sh" smoke; then
  echo "Smoke failed; not starting live experiments." >&2
  exit 1
fi

if ! run_stage 02_validate bash "$HERE/launch.sh" validate "$MANIFEST"; then
  echo "Manifest validation failed; not starting live experiments." >&2
  exit 1
fi

if ! run_stage 03_source_audit python3 "$HERE/verify_case_evidence.py" --cache "$WORKDIR/cache"; then
  echo "Historical source audit failed; not starting live experiments." >&2
  exit 1
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader \
    > "$LOG_DIR/gpu_info.txt" 2>&1 || true
fi
{
  python3 --version
  git --version
  if command -v ollama >/dev/null 2>&1; then ollama --version; fi
  if [[ -d "$UPSTREAM_DIR/.git" ]]; then
    printf 'DocAgent_commit: '
    git -C "$UPSTREAM_DIR" rev-parse HEAD
  fi
  if [[ -d "$HERE/../.git" ]]; then
    printf 'Experiment_wrapper_commit: '
    git -C "$HERE/.." rev-parse HEAD
  fi
} > "$LOG_DIR/versions.txt" 2>&1 || true

if [[ "${SKIP_DEMO:-0}" == "1" ]]; then
  printf '04_demo\tskipped\n' >> "$BATCH_DIR/stage_status.tsv"
else
  if ! run_stage 04_demo bash "$HERE/launch.sh" demo; then
    echo "Synthetic C00 demo failed; see log. Continuing to attempt real cases." >&2
  fi
fi

failed=0
for case_id in C01 C02 C03 C04; do
  if ! run_stage "10_$case_id" bash "$HERE/launch.sh" run "$MANIFEST" "$case_id"; then
    echo "WARNING: $case_id failed. Other cases will still run." >&2
    failed=1
  fi
done

if ! run_stage 20_report bash "$HERE/launch.sh" report real; then
  echo "WARNING: report step failed; preserving all original traces." >&2
  failed=1
fi

if [[ "$failed" -eq 0 ]]; then
  echo "All run commands finished. Check individual oracle verdicts in the ZIP."
else
  echo "Some cases or reporting failed. The ZIP will flag missing/partial runs." >&2
fi
exit "$failed"
