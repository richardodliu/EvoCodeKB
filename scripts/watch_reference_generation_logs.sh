#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS_BASE_DIR="${REPO_ROOT}/benchmark/runs/reference_gen_qwen25coder7b"
LATEST_RUN_META="${RUNS_BASE_DIR}/latest_run.json"

RUN_DIR=""
RANK=""
ALL_RANKS=0
FOLLOW=1
LINES=40

usage() {
  cat <<'EOF'
Usage: bash scripts/watch_reference_generation_logs.sh [options]

Options:
  --run-dir PATH    Use a specific run directory instead of latest
  --latest          Use the latest submitted run (default)
  --rank N          Watch only run.rankN.log
  --all-ranks       Watch controller log plus all existing rank logs
  --lines N         Number of tail lines to show first (default: 40)
  --no-follow       Print tail output once without following
  --help            Show this help
EOF
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
  python - "${meta_path}" <<'PY'
import json
import shlex
import sys

meta = json.load(open(sys.argv[1], "r", encoding="utf-8"))
mapping = {
    "run_dir": "META_RUN_DIR",
    "controller_log": "META_CONTROLLER_LOG",
    "num_gpus": "META_NUM_GPUS",
}
for key, env_name in mapping.items():
    value = meta.get(key)
    if value is None:
        value = ""
    print(f"{env_name}={shlex.quote(str(value))}")
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    --latest)
      shift
      ;;
    --rank)
      RANK="$2"
      shift 2
      ;;
    --all-ranks)
      ALL_RANKS=1
      shift
      ;;
    --lines)
      LINES="$2"
      shift 2
      ;;
    --no-follow)
      FOLLOW=0
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

if [[ -n "${RANK}" && "${ALL_RANKS}" -eq 1 ]]; then
  echo "--rank and --all-ranks cannot be used together" >&2
  exit 1
fi
if (( LINES <= 0 )); then
  echo "--lines must be > 0" >&2
  exit 1
fi

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

if [[ -z "${META_RUN_DIR}" ]]; then
  echo "run_dir missing from metadata: ${META_SOURCE}" >&2
  exit 1
fi

declare -a files=()
if (( ALL_RANKS == 1 )); then
  if [[ -f "${META_CONTROLLER_LOG}" ]]; then
    files+=("${META_CONTROLLER_LOG}")
  fi
  for rank_index in $(seq 0 $((META_NUM_GPUS - 1))); do
    rank_log="${META_RUN_DIR}/run.rank${rank_index}.log"
    if [[ -f "${rank_log}" ]]; then
      files+=("${rank_log}")
    fi
  done
else
  if [[ -n "${RANK}" ]]; then
    rank_log="${META_RUN_DIR}/run.rank${RANK}.log"
    if [[ ! -f "${rank_log}" ]]; then
      echo "Rank log not found: ${rank_log}" >&2
      exit 1
    fi
    files+=("${rank_log}")
  else
    if [[ ! -f "${META_CONTROLLER_LOG}" ]]; then
      echo "Controller log not found: ${META_CONTROLLER_LOG}" >&2
      exit 1
    fi
    files+=("${META_CONTROLLER_LOG}")
  fi
fi

if (( ${#files[@]} == 0 )); then
  echo "No log files available under ${META_RUN_DIR}" >&2
  exit 1
fi

echo "Run dir: ${META_RUN_DIR}"
for file_path in "${files[@]}"; do
  echo "Watching: ${file_path}"
done

if (( FOLLOW == 1 )); then
  tail -n "${LINES}" -f "${files[@]}"
else
  tail -n "${LINES}" "${files[@]}"
fi
