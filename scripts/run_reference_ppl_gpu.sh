#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_ACTIVATE="/volume/pt-train/users/rbliu/miniconda3/bin/activate"
ENV_NAME="evokb"

REMOTE_USER="root"
REMOTE_HOST="183.242.150.6"
REMOTE_PORT="32045"

RUNS_BASE_DIR="${REPO_ROOT}/benchmark/runs/reference_ppl_qwen25coder7b"
LATEST_RUN_META="${RUNS_BASE_DIR}/latest_run.json"

INPUT_PATH="${REPO_ROOT}/benchmark/output_n5_max100_shots10_information_2gram.jsonl"
OUTPUT_DIR=""
OUTPUT_JSONL="${REPO_ROOT}/benchmark/output_n5_max100_shots10_information_2gram_log_ppl.jsonl"
MODEL_PATH="/volume/pt-train/users/rbliu/model/Qwen2.5-Coder-7B"

REFERENCE_SHOTS=5
PROMPT_TAIL_LINES=5
LIMIT=-1
NUM_GPUS=8
FOREGROUND=0

usage() {
  cat <<'EOF'
Usage: bash scripts/run_reference_ppl_gpu.sh [options]

Options:
  --input PATH               Input JSONL path
  --output-dir PATH          Exact run directory to use
  --output-jsonl PATH        Final augmented JSONL output path
  --model-path PATH          Local model directory
  --reference-shots N        Keep only the first N references per sample (default: 5)
  --prompt-tail-lines N      Keep only the last N prompt lines (default: 5)
  --limit N                  Only process the first N samples before sharding
  --num-gpus N               Number of single-card workers to launch (default: 8)
  --user USER                Remote SSH user (default: root)
  --host HOST                Remote SSH host (default: 183.242.150.6)
  --port PORT                Remote SSH port (default: 32045)
  --foreground               Run the remote controller in foreground
  --help                     Show this help
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

make_default_run_dir() {
  local timestamp run_name run_dir suffix
  timestamp="$(date -u +%Y%m%d_%H%M%S)"
  run_name="${timestamp}_r${REFERENCE_SHOTS}_n${PROMPT_TAIL_LINES}_g${NUM_GPUS}"
  if (( LIMIT > 0 )); then
    run_name="${run_name}_limit${LIMIT}"
  fi

  run_dir="${RUNS_BASE_DIR}/${run_name}"
  suffix=0
  while [[ -e "${run_dir}" ]]; do
    suffix=$((suffix + 1))
    run_dir="${RUNS_BASE_DIR}/${run_name}_${suffix}"
  done
  printf '%s\n' "${run_dir}"
}

write_run_meta() {
  local run_meta_path="$1"
  local latest_meta_path="$2"

  RUN_DIR="${RUN_DIR}" \
  OUTPUT_JSONL="${OUTPUT_JSONL}" \
  NUM_GPUS="${NUM_GPUS}" \
  PROMPT_TAIL_LINES="${PROMPT_TAIL_LINES}" \
  REFERENCE_SHOTS="${REFERENCE_SHOTS}" \
  SUBMITTED_AT="${SUBMITTED_AT}" \
  SUBMISSION_MODE="${SUBMISSION_MODE}" \
  REMOTE_USER="${REMOTE_USER}" \
  REMOTE_HOST="${REMOTE_HOST}" \
  REMOTE_PORT="${REMOTE_PORT}" \
  REPO_ROOT="${REPO_ROOT}" \
  CONDA_ACTIVATE="${CONDA_ACTIVATE}" \
  ENV_NAME="${ENV_NAME}" \
  INPUT_PATH="${INPUT_PATH}" \
  MODEL_PATH="${MODEL_PATH}" \
  LIMIT="${LIMIT}" \
  REMOTE_PID_VALUE="${REMOTE_PID_VALUE:-}" \
  REMOTE_PGID_VALUE="${REMOTE_PGID_VALUE:-}" \
  RUN_META_PATH="${run_meta_path}" \
  LATEST_META_PATH="${latest_meta_path}" \
  python - <<'PY2'
import json
import os
from pathlib import Path


def optional_int(name: str):
    value = os.environ.get(name, '')
    if not value:
        return None
    return int(value)


run_dir = os.environ['RUN_DIR']
num_gpus = int(os.environ['NUM_GPUS'])
controller_log = f'{run_dir}/run.log'
controller_script = f'{run_dir}/controller.sh'
meta = {
    'run_name': Path(run_dir).name,
    'run_dir': run_dir,
    'run_meta_path': os.environ['RUN_META_PATH'],
    'submitted_at': os.environ['SUBMITTED_AT'],
    'submission_mode': os.environ['SUBMISSION_MODE'],
    'ssh_user': os.environ['REMOTE_USER'],
    'ssh_host': os.environ['REMOTE_HOST'],
    'ssh_port': optional_int('REMOTE_PORT'),
    'remote_repo_root': os.environ['REPO_ROOT'],
    'conda_activate': os.environ['CONDA_ACTIVATE'],
    'env_name': os.environ['ENV_NAME'],
    'input_path': os.environ['INPUT_PATH'],
    'output_jsonl': os.environ['OUTPUT_JSONL'],
    'model_path': os.environ['MODEL_PATH'],
    'reference_shots': int(os.environ['REFERENCE_SHOTS']),
    'prompt_tail_lines': int(os.environ['PROMPT_TAIL_LINES']),
    'limit': int(os.environ['LIMIT']),
    'num_gpus': num_gpus,
    'controller_script': controller_script,
    'controller_log': controller_log,
    'rank_logs': [f'{run_dir}/run.rank{rank}.log' for rank in range(num_gpus)],
    'remote_pid': optional_int('REMOTE_PID_VALUE'),
    'remote_pgid': optional_int('REMOTE_PGID_VALUE'),
}

for target_path in (Path(os.environ['RUN_META_PATH']), Path(os.environ['LATEST_META_PATH'])):
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
PY2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      INPUT_PATH="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --output-jsonl)
      OUTPUT_JSONL="$2"
      shift 2
      ;;
    --model-path)
      MODEL_PATH="$2"
      shift 2
      ;;
    --reference-shots)
      REFERENCE_SHOTS="$2"
      shift 2
      ;;
    --prompt-tail-lines)
      PROMPT_TAIL_LINES="$2"
      shift 2
      ;;
    --limit)
      LIMIT="$2"
      shift 2
      ;;
    --num-gpus)
      NUM_GPUS="$2"
      shift 2
      ;;
    --user)
      REMOTE_USER="$2"
      shift 2
      ;;
    --host)
      REMOTE_HOST="$2"
      shift 2
      ;;
    --port)
      REMOTE_PORT="$2"
      shift 2
      ;;
    --foreground)
      FOREGROUND=1
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

INPUT_PATH="$(abspath "${INPUT_PATH}")"
OUTPUT_JSONL="$(abspath "${OUTPUT_JSONL}")"
MODEL_PATH="$(abspath "${MODEL_PATH}")"

if [[ -n "${OUTPUT_DIR}" ]]; then
  RUN_DIR="$(abspath "${OUTPUT_DIR}")"
else
  RUN_DIR="$(make_default_run_dir)"
fi

RUN_META_PATH="${RUN_DIR}/run_meta.json"

if [[ ! -f "${CONDA_ACTIVATE}" ]]; then
  echo "Conda activate script not found: ${CONDA_ACTIVATE}" >&2
  exit 1
fi
if [[ ! -d "${REPO_ROOT}" ]]; then
  echo "Repository root not found: ${REPO_ROOT}" >&2
  exit 1
fi
if [[ ! -f "${INPUT_PATH}" ]]; then
  echo "Input JSONL not found: ${INPUT_PATH}" >&2
  exit 1
fi
if [[ ! -d "${MODEL_PATH}" ]]; then
  echo "Model directory not found: ${MODEL_PATH}" >&2
  exit 1
fi
if (( REFERENCE_SHOTS <= 0 )); then
  echo "--reference-shots must be > 0" >&2
  exit 1
fi
if (( PROMPT_TAIL_LINES <= 0 )); then
  echo "--prompt-tail-lines must be > 0" >&2
  exit 1
fi
if (( NUM_GPUS <= 0 )); then
  echo "--num-gpus must be > 0" >&2
  exit 1
fi
if (( LIMIT == 0 || LIMIT < -1 )); then
  echo "--limit must be -1 or a positive integer" >&2
  exit 1
fi

mkdir -p "${RUNS_BASE_DIR}"
if [[ -e "${RUN_DIR}" ]]; then
  if find "${RUN_DIR}" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    echo "Run directory already exists and is not empty: ${RUN_DIR}" >&2
    exit 1
  fi
else
  mkdir -p "${RUN_DIR}"
fi

SSH_TARGET="${REMOTE_USER}@${REMOTE_HOST}"
SSH_OPTS=(
  -o BatchMode=yes
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=10
  -o LogLevel=ERROR
  -p "${REMOTE_PORT}"
)

MODE='background'
if (( FOREGROUND == 1 )); then
  MODE='foreground'
fi

echo 'Submitting reference PPL job via SSH'
echo "Remote target: ${SSH_TARGET}:${REMOTE_PORT}"
echo "Run dir: ${RUN_DIR}"
echo "Input: ${INPUT_PATH}"
echo "Output JSONL: ${OUTPUT_JSONL}"
echo "Model: ${MODEL_PATH}"
echo "Reference shots: ${REFERENCE_SHOTS}"
echo "Prompt tail lines: ${PROMPT_TAIL_LINES}"
echo "Num GPUs: ${NUM_GPUS}"
if (( LIMIT > 0 )); then
  echo "Limit: ${LIMIT}"
fi

remote_submit() {
  local mode="$1"
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" bash -s -- \
    "${mode}" \
    "${CONDA_ACTIVATE}" \
    "${ENV_NAME}" \
    "${REPO_ROOT}" \
    "${INPUT_PATH}" \
    "${RUN_DIR}" \
    "${OUTPUT_JSONL}" \
    "${MODEL_PATH}" \
    "${REFERENCE_SHOTS}" \
    "${PROMPT_TAIL_LINES}" \
    "${LIMIT}" \
    "${NUM_GPUS}" <<'REMOTE'
set -euo pipefail

MODE="$1"
CONDA_ACTIVATE="$2"
ENV_NAME="$3"
REPO_ROOT="$4"
INPUT_PATH="$5"
RUN_DIR="$6"
OUTPUT_JSONL="$7"
MODEL_PATH="$8"
REFERENCE_SHOTS="$9"
PROMPT_TAIL_LINES="${10}"
LIMIT="${11}"
NUM_GPUS="${12}"

mkdir -p "${RUN_DIR}"
mkdir -p "$(dirname "${OUTPUT_JSONL}")"
CONTROLLER_SCRIPT="${RUN_DIR}/controller.sh"
REMOTE_LOG="${RUN_DIR}/run.log"

cat > "${CONTROLLER_SCRIPT}" <<'CONTROLLER'
#!/usr/bin/env bash
set -euo pipefail

CONDA_ACTIVATE="$1"
ENV_NAME="$2"
REPO_ROOT="$3"
INPUT_PATH="$4"
RUN_DIR="$5"
OUTPUT_JSONL="$6"
MODEL_PATH="$7"
REFERENCE_SHOTS="$8"
PROMPT_TAIL_LINES="$9"
LIMIT="${10}"
NUM_GPUS="${11}"

source "${CONDA_ACTIVATE}" "${ENV_NAME}"
cd "${REPO_ROOT}"

echo "Controller started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Controller PID=$$ PGID=$(ps -o pgid= -p $$ | tr -d ' ')"
echo "Reference shots=${REFERENCE_SHOTS}"
echo "Prompt tail lines=${PROMPT_TAIL_LINES}"

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

WORKER_SCRIPT="${REPO_ROOT}/scripts/eval_reference_ppl.py"
MERGE_SCRIPT="${REPO_ROOT}/scripts/merge_reference_ppl_results.py"

pids=()
for rank in $(seq 0 $((NUM_GPUS - 1))); do
  worker_log="${RUN_DIR}/run.rank${rank}.log"
  worker_cmd=(
    python "${WORKER_SCRIPT}"
    --input "${INPUT_PATH}"
    --output-dir "${RUN_DIR}"
    --model-path "${MODEL_PATH}"
    --reference-shots "${REFERENCE_SHOTS}"
    --prompt-tail-lines "${PROMPT_TAIL_LINES}"
    --num-shards "${NUM_GPUS}"
    --shard-rank "${rank}"
  )
  if [[ "${LIMIT}" -gt 0 ]]; then
    worker_cmd+=(--limit "${LIMIT}")
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

echo 'All workers finished. Merging shard outputs.'
python "${MERGE_SCRIPT}" \
  --input "${INPUT_PATH}" \
  --output-dir "${RUN_DIR}" \
  --output-jsonl "${OUTPUT_JSONL}" \
  --num-shards "${NUM_GPUS}"
echo "Merge completed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
CONTROLLER

chmod +x "${CONTROLLER_SCRIPT}"

if [[ "${MODE}" = 'background' ]]; then
  setsid bash "${CONTROLLER_SCRIPT}" \
    "${CONDA_ACTIVATE}" \
    "${ENV_NAME}" \
    "${REPO_ROOT}" \
    "${INPUT_PATH}" \
    "${RUN_DIR}" \
    "${OUTPUT_JSONL}" \
    "${MODEL_PATH}" \
    "${REFERENCE_SHOTS}" \
    "${PROMPT_TAIL_LINES}" \
    "${LIMIT}" \
    "${NUM_GPUS}" > "${REMOTE_LOG}" 2>&1 < /dev/null &
  CONTROLLER_PID="$!"
  sleep 1
  CONTROLLER_PGID="$(ps -o pgid= -p "${CONTROLLER_PID}" | tr -d ' ')"
  if [[ -z "${CONTROLLER_PGID}" ]]; then
    CONTROLLER_PGID="${CONTROLLER_PID}"
  fi
  if ! kill -0 "${CONTROLLER_PID}" 2>/dev/null; then
    echo 'Controller failed to start' >&2
    exit 1
  fi

  echo "RUN_DIR=${RUN_DIR}"
  echo "LOG_PATH=${REMOTE_LOG}"
  echo "CONTROLLER_SCRIPT=${CONTROLLER_SCRIPT}"
  echo "REMOTE_PID=${CONTROLLER_PID}"
  echo "REMOTE_PGID=${CONTROLLER_PGID}"
else
  echo "RUN_DIR=${RUN_DIR}"
  echo "LOG_PATH=${REMOTE_LOG}"
  echo "CONTROLLER_SCRIPT=${CONTROLLER_SCRIPT}"
  bash "${CONTROLLER_SCRIPT}" \
    "${CONDA_ACTIVATE}" \
    "${ENV_NAME}" \
    "${REPO_ROOT}" \
    "${INPUT_PATH}" \
    "${RUN_DIR}" \
    "${OUTPUT_JSONL}" \
    "${MODEL_PATH}" \
    "${REFERENCE_SHOTS}" \
    "${PROMPT_TAIL_LINES}" \
    "${LIMIT}" \
    "${NUM_GPUS}" 2>&1 | tee "${REMOTE_LOG}"
fi
REMOTE
}

if [[ "${MODE}" = 'background' ]]; then
  SUBMIT_OUTPUT="$(remote_submit "${MODE}")"
  printf '%s\n' "${SUBMIT_OUTPUT}"

  REMOTE_PID_VALUE="$(printf '%s\n' "${SUBMIT_OUTPUT}" | sed -n 's/^REMOTE_PID=//p' | tail -n 1)"
  REMOTE_PGID_VALUE="$(printf '%s\n' "${SUBMIT_OUTPUT}" | sed -n 's/^REMOTE_PGID=//p' | tail -n 1)"
  REPORTED_RUN_DIR="$(printf '%s\n' "${SUBMIT_OUTPUT}" | sed -n 's/^RUN_DIR=//p' | tail -n 1)"

  if [[ -z "${REMOTE_PID_VALUE}" || -z "${REMOTE_PGID_VALUE}" ]]; then
    echo 'Failed to parse remote PID/PGID from SSH response.' >&2
    exit 1
  fi
  if [[ -n "${REPORTED_RUN_DIR}" && "${REPORTED_RUN_DIR}" != "${RUN_DIR}" ]]; then
    echo "Remote reported unexpected run directory: ${REPORTED_RUN_DIR}" >&2
    exit 1
  fi

  SUBMITTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  SUBMISSION_MODE="${MODE}"
  write_run_meta "${RUN_META_PATH}" "${LATEST_RUN_META}"

  echo "Run metadata: ${RUN_META_PATH}"
  echo 'Watch log: bash scripts/watch_reference_ppl_logs.sh'
  echo 'Check status: bash scripts/status_reference_ppl_run.sh'
  echo 'Kill run: bash scripts/kill_reference_ppl_run.sh'
else
  remote_submit "${MODE}"
  REMOTE_PID_VALUE=''
  REMOTE_PGID_VALUE=''
  SUBMITTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  SUBMISSION_MODE="${MODE}"
  write_run_meta "${RUN_META_PATH}" "${LATEST_RUN_META}"

  echo 'Foreground run completed.'
  echo "Run metadata: ${RUN_META_PATH}"
fi
