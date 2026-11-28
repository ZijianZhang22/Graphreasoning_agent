#!/usr/bin/env bash
# Prepare a fresh RunPod (PyTorch template). Uses no GitHub credentials.
# Requires a persistent /workspace disk and Internet access.
set -Eeuo pipefail

TASK2_ROOT="/workspace/docagent-task1/DocAgent"
MODEL_DIR="/workspace/ollama-models"
PIN_SHA="d44ab1bb365fb7c151577dbd321a52fbf06d38ae"

command -v nvidia-smi >/dev/null || { echo 'ERROR: No NVIDIA GPU detected. Check RunPod type/template.' >&2; exit 2; }
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
for cmd in git curl unzip python3; do
  if ! command -v "$cmd" >/dev/null; then
    if command -v apt-get >/dev/null && [ "$(id -u)" -eq 0 ]; then
      apt-get update -qq && apt-get install -y -qq git curl unzip python3
      break
    else
      echo "Missing required command: $cmd" >&2; exit 2
    fi
  fi
done

mkdir -p /workspace/docagent-task1 /workspace/docagent-task2 "$MODEL_DIR"
if ! [ -d "$TASK2_ROOT/.git" ]; then
  git clone https://github.com/xiangruiSun/DocAgent.git "$TASK2_ROOT"
fi
cd "$TASK2_ROOT"
git fetch --quiet origin "$PIN_SHA" || true
if ! git cat-file -e "$PIN_SHA^{commit}" 2>/dev/null; then
  echo "ERROR: Pin $PIN_SHA unavailable; do NOT silently replace with HEAD" >&2
  exit 2
fi
git checkout --detach --quiet "$PIN_SHA"
cat <<EOF
DocAgent pinned commit: $(git rev-parse HEAD)
Task 2 benchmark: $TASK2_ROOT/experiments/paired_runs/bench.py
EOF

if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
# Only launch an Ollama server if one is not already reachable.
# If a server is already running, the host configuration determines its model directory.
if ! curl -fsS --max-time 4 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo 'Starting Ollama server with persistent model directory...'
  OLLAMA_MODELS="$MODEL_DIR" OLLAMA_HOST='127.0.0.1:11434' \
    nohup ollama serve >/workspace/ollama-serve.log 2>&1 </dev/null &
  for i in $(seq 1 30); do
    if curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then break; fi
    sleep 2
  done
fi
curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags >/dev/null || {
  echo 'ERROR: Ollama did not start. View /workspace/ollama-serve.log' >&2; exit 2;
}
export OLLAMA_MODELS="$MODEL_DIR"
ollama pull qwen3-coder:30b
ollama list

echo 'READY. Next: use python3 solve_only_task2.py preflight, then smoke, prepare, pilot, heldout, export.'
