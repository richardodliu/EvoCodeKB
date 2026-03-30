#!/usr/bin/env bash
set -euo pipefail

CONDA_ACTIVATE="$1"
ENV_NAME="$2"
REPO_ROOT="$3"
INPUT_PATH="$4"
RUN_DIR="$5"
OUTPUT_JSONL="$6"
MODEL_PATH="$7"
PROMPT_BUILDER="$9"
STOP_POLICY="${10}"
DECODE_POLICY="${11}"
BEAM_SIZE="${12}"
REFERENCE_SHOTS="${14}"
MAX_NEW_TOKENS="${15}"
LIMIT="${16}"
NUM_GPUS="${17}"
SPLIT_MOD="${18}"
SPLIT_REM="${19}"

source "${CONDA_ACTIVATE}" "${ENV_NAME}"
cd "${REPO_ROOT}"

echo "Controller started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Controller PID=$$ PGID=$(ps -o pgid= -p $$ | tr -d ' ')"
echo "Builder=${PROMPT_BUILDER} stop=${STOP_POLICY} decode=${DECODE_POLICY}"

python - <<'PY3'
import importlib

modules = ['torch', 'transformers', 'accelerate', 'sentencepiece']
missing = []
for name in modules:
    try:
        importlib.import_module(name)
    except Exception:
        missing.append(name)
if missing:
    raise SystemExit('Missing Python packages: ' + ', '.join(missing))
PY3

python - "${NUM_GPUS}" <<'PY4'
import sys
import torch

required = int(sys.argv[1])
count = torch.cuda.device_count()
if count < required:
    raise SystemExit(f'Expected at least {required} CUDA devices, found {count}')
print(f'Detected {count} CUDA devices; launching {required} workers.', flush=True)
PY4

WORKER_SCRIPT="${REPO_ROOT}/scripts/eval_reference_generation.py"
MERGE_SCRIPT="${REPO_ROOT}/scripts/merge_reference_generation_results.py"

pids=()
for rank in $(seq 0 $((NUM_GPUS - 1))); do
  worker_log="${RUN_DIR}/run.rank${rank}.log"
  worker_cmd=(
    python "${WORKER_SCRIPT}"
    --input "${INPUT_PATH}"
    --output-dir "${RUN_DIR}"
    --model-path "${MODEL_PATH}"
    --prompt-builder "${PROMPT_BUILDER}"
    --stop-policy "${STOP_POLICY}"
    --decode-policy "${DECODE_POLICY}"
    --beam-size "${BEAM_SIZE}"
    --reference-shots "${REFERENCE_SHOTS}"
    --max-new-tokens "${MAX_NEW_TOKENS}"
    --num-shards "${NUM_GPUS}"
    --shard-rank "${rank}"
  )
  if [[ "${LIMIT}" -gt 0 ]]; then
    worker_cmd+=(--limit "${LIMIT}")
  fi
  if [[ "${SPLIT_MOD}" -gt 0 ]]; then
    worker_cmd+=(--split-mod "${SPLIT_MOD}" --split-rem "${SPLIT_REM}")
  fi
  echo "Starting rank ${rank}; log=${worker_log}" | tee -a "${worker_log}"
  CUDA_VISIBLE_DEVICES="${rank}" "${worker_cmd[@]}" >> "${worker_log}" 2>&1 &
  pids+=("$!")
done

failures=0
for pid in "${pids[@]}"; do
  if ! wait "${pid}"; then
    failures=$((failures + 1))
  fi
done

if [[ "${failures}" -ne 0 ]]; then
  echo "${failures} worker(s) failed; skipping merge." >&2
  exit 1
fi

echo 'All workers finished. Merging generation shard outputs.'
python "${MERGE_SCRIPT}" \
  --input "${INPUT_PATH}" \
  --output-dir "${RUN_DIR}" \
  --output-jsonl "${OUTPUT_JSONL}" \
  --num-shards "${NUM_GPUS}"
echo "Merge completed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
