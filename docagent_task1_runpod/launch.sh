#!/usr/bin/env bash
# RunPod launcher for DocAgent Task 1. Does not modify the upstream repository.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="${DOCAGENT_WORKDIR:-/workspace/docagent-task1}"
UPSTREAM_DIR="${DOCAGENT_UPSTREAM_DIR:-$WORKDIR/DocAgent}"
UPSTREAM_REF="d44ab1bb365fb7c151577dbd321a52fbf06d38ae"
UPSTREAM_URL="https://github.com/xiangruiSun/DocAgent.git"
MODEL="${QWEN_MODEL:-qwen3:8b}"
RUNS_DIR="${DOCAGENT_RUNS_DIR:-$WORKDIR/runs}"
BACKEND_CONFIG="$WORKDIR/backend.runpod.json"
CASE_DRIVER="$UPSTREAM_DIR/experiments/case_studies/cases.py"

usage() {
  cat <<'EOF'
Usage:
  bash launch.sh setup                  Install/start Ollama, pull Qwen3:8b, clone pinned DocAgent
  bash launch.sh smoke                  Run no-model fake backend smoke test
  bash launch.sh demo                   Run both real-model arms on synthetic C00 (NOT research data)
  bash launch.sh validate CASES_JSON    Check case manifests and old/new revisions
  bash launch.sh run CASES_JSON CASE_ID  Run blind + checked on a prepared genuine case
  bash launch.sh report [real|demo]     Generate offline reports and PPT-friendly summaries
  bash launch.sh status                 Print local Git/Ollama/GPU status

Environment: DOCAGENT_WORKDIR, DOCAGENT_UPSTREAM_DIR, DOCAGENT_RUNS_DIR,
             QWEN_MODEL (default qwen3:8b), TASK1_TIME_S (180), TASK1_ACTIONS (8).
EOF
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 1; }
}

ensure_upstream() {
  require_tool git
  mkdir -p "$WORKDIR"
  if [[ ! -d "$UPSTREAM_DIR/.git" ]]; then
    echo "Cloning DocAgent at reproducible commit $UPSTREAM_REF"
    git clone -q "$UPSTREAM_URL" "$UPSTREAM_DIR"
    git -C "$UPSTREAM_DIR" checkout -q --detach "$UPSTREAM_REF"
  fi
  local actual
  actual="$(git -C "$UPSTREAM_DIR" rev-parse HEAD)"
  if [[ "$actual" != "$UPSTREAM_REF" ]]; then
    echo "Existing DocAgent is at $actual, expected $UPSTREAM_REF." >&2
    echo "Use a different DOCAGENT_WORKDIR to avoid changing an existing checkout." >&2
    exit 2
  fi
  [[ -f "$CASE_DRIVER" ]] || { echo "Missing case driver: $CASE_DRIVER" >&2; exit 2; }
}

start_ollama() {
  require_tool curl
  if curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama is running locally."
    return
  fi
  require_tool ollama
  mkdir -p "$WORKDIR"
  nohup ollama serve >"$WORKDIR/ollama.log" 2>&1 </dev/null &
  for ((i=0;i<60;i++)); do
    if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      echo "Started Ollama."
      return
    fi
    sleep 1
  done
  echo "Ollama failed to start; see $WORKDIR/ollama.log" >&2
  exit 2
}

write_backend() {
  require_tool python3
  mkdir -p "$WORKDIR"
  python3 - "$HERE/backend.runpod.json" "$BACKEND_CONFIG" "$MODEL" <<'PY'
import json
from pathlib import Path
import sys
src, dest, model = sys.argv[1:]
conf = json.loads(Path(src).read_text(encoding="utf-8"))
conf["name"] = "runpod-" + model.replace(":", "-")
conf["settings"]["model"] = model
Path(dest).write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")
print("Backend config:", dest, "model:", model)
PY
}

require_live_backend() {
  require_tool curl
  curl -fsS --max-time 4 http://127.0.0.1:11434/api/tags >/dev/null ||
    { echo "Ollama not reachable. Run: bash launch.sh setup" >&2; exit 2; }
  write_backend
  ollama list
}

run_case() {
  local manifest="$1" case_id="$2" group="$3"
  [[ -f "$manifest" ]] || { echo "Manifest not found: $manifest" >&2; exit 2; }
  ensure_upstream
  require_live_backend
  mkdir -p "$RUNS_DIR/$group"
  python3 "$CASE_DRIVER" run \
    --manifest "$(realpath "$manifest")" \
    --case "$case_id" --arm both \
    --backend-config "$BACKEND_CONFIG" \
    --time-s "${TASK1_TIME_S:-180}" \
    --max-actions "${TASK1_ACTIONS:-8}" \
    --cache "$WORKDIR/cache" \
    --out "$RUNS_DIR/$group"
  echo "Run artifacts: $RUNS_DIR/$group/$case_id"
  python3 "$CASE_DRIVER" report --runs "$RUNS_DIR/$group" --out "$RUNS_DIR/$group/reports"
  python3 "$HERE/summarize.py" --runs "$RUNS_DIR/$group" --out "$RUNS_DIR/$group/summary"
}

cmd="${1:-help}"
case "$cmd" in
  setup)
    require_tool python3
    require_tool git
    require_tool curl
    if ! command -v ollama >/dev/null 2>&1; then
      echo "Installing Ollama from its official installation script."
      curl -fsSL https://ollama.com/install.sh | sh
    fi
    ensure_upstream
    start_ollama
    echo "Pulling $MODEL (this may download several GB)."
    ollama pull "$MODEL"
    write_backend
    echo "Setup complete. Next: bash launch.sh smoke && bash launch.sh demo"
    ;;
  smoke)
    ensure_upstream
    python3 "$CASE_DRIVER" smoke --backend fake
    ;;
  demo)
    ensure_upstream
    run_case "$UPSTREAM_DIR/experiments/case_studies/cases.example.json" C00 demo
    echo "IMPORTANT: C00 is researcher-constructed and is NOT a genuine historical case."
    ;;
  validate)
    [[ $# -eq 2 ]] || { usage; exit 2; }
    ensure_upstream
    python3 "$CASE_DRIVER" validate --manifest "$(realpath "$2")" --cache "$WORKDIR/cache"
    ;;
  run)
    [[ $# -eq 3 ]] || { usage; exit 2; }
    run_case "$2" "$3" real
    ;;
  report)
    [[ $# -le 2 ]] || { usage; exit 2; }
    ensure_upstream
    group="${2:-real}"
    [[ "$group" == "real" || "$group" == "demo" ]] || { echo "group must be real or demo"; exit 2; }
    python3 "$CASE_DRIVER" report --runs "$RUNS_DIR/$group" --out "$RUNS_DIR/$group/reports"
    python3 "$HERE/summarize.py" --runs "$RUNS_DIR/$group" --out "$RUNS_DIR/$group/summary"
    ;;
  status)
    echo "Workdir: $WORKDIR"
    echo "Expected DocAgent SHA: $UPSTREAM_REF"
    if [[ -d "$UPSTREAM_DIR/.git" ]]; then git -C "$UPSTREAM_DIR" rev-parse HEAD; fi
    if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi; fi
    if command -v ollama >/dev/null 2>&1; then ollama list || true; fi
    ;;
  help|-h|--help) usage ;;
  *) usage; exit 2 ;;
esac
