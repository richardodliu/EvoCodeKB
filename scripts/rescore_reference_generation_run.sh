#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS_BASE_DIR="${REPO_ROOT}/benchmark/runs/reference_gen_qwen25coder7b"
LATEST_RUN_META="${RUNS_BASE_DIR}/latest_run.json"

RUN_DIR=""
OUTPUT_JSONL=""

usage() {
  cat <<'USAGE'
Usage: bash scripts/rescore_reference_generation_run.sh [options]

Options:
  --run-dir PATH       Re-score a specific run directory instead of latest
  --output-jsonl PATH  Override final augmented JSONL output path
  --latest             Use the latest submitted run (default)
  --help               Show this help
USAGE
}

abspath() {
  local path="$1"
  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
  else
    printf '%s\n' "${REPO_ROOT}/${path#./}"
  fi
}

load_meta_env() {
  local meta_path="$1"
  python - "${meta_path}" <<'PYMETA'
import json
import shlex
import sys

meta = json.load(open(sys.argv[1], 'r', encoding='utf-8'))
mapping = {
    'run_dir': 'META_RUN_DIR',
    'input_path': 'META_INPUT_PATH',
    'output_jsonl': 'META_OUTPUT_JSONL',
    'num_gpus': 'META_NUM_GPUS',
}
for key, env_name in mapping.items():
    value = meta.get(key)
    if value is None:
        value = ''
    print(f"{env_name}={shlex.quote(str(value))}")
PYMETA
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    --output-jsonl)
      OUTPUT_JSONL="$2"
      shift 2
      ;;
    --latest)
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -n "${RUN_DIR}" ]]; then
  META_SOURCE="$(abspath "${RUN_DIR}")/run_meta.json"
else
  META_SOURCE="${LATEST_RUN_META}"
fi

if [[ ! -f "${META_SOURCE}" ]]; then
  echo "Run metadata not found: ${META_SOURCE}" >&2
  exit 1
fi

eval "$(load_meta_env "${META_SOURCE}")"

if [[ -z "${META_RUN_DIR}" || -z "${META_INPUT_PATH}" || -z "${META_OUTPUT_JSONL}" || -z "${META_NUM_GPUS}" ]]; then
  echo "Incomplete run metadata: ${META_SOURCE}" >&2
  exit 1
fi

if [[ -n "${OUTPUT_JSONL}" ]]; then
  FINAL_OUTPUT_JSONL="$(abspath "${OUTPUT_JSONL}")"
else
  FINAL_OUTPUT_JSONL="${META_OUTPUT_JSONL}"
fi

echo "Re-scoring generation run"
echo "Run dir: ${META_RUN_DIR}"
echo "Input: ${META_INPUT_PATH}"
echo "Output JSONL: ${FINAL_OUTPUT_JSONL}"
echo "Num shards: ${META_NUM_GPUS}"

python "${REPO_ROOT}/scripts/merge_reference_generation_results.py"   --input "${META_INPUT_PATH}"   --output-dir "${META_RUN_DIR}"   --output-jsonl "${FINAL_OUTPUT_JSONL}"   --num-shards "${META_NUM_GPUS}"
