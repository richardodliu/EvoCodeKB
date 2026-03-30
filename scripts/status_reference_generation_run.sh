#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS_BASE_DIR="${REPO_ROOT}/benchmark/runs/reference_gen_qwen25coder7b"
LATEST_RUN_META="${RUNS_BASE_DIR}/latest_run.json"

RUN_DIR=""
LINES=20

usage() {
  cat <<'EOF'
Usage: bash scripts/status_reference_generation_run.sh [options]

Options:
  --run-dir PATH    Use a specific run directory instead of latest
  --latest          Use the latest submitted run (default)
  --lines N         Show the last N lines from run.log (default: 20)
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
    "run_meta_path": "META_RUN_META_PATH",
    "controller_log": "META_CONTROLLER_LOG",
    "controller_script": "META_CONTROLLER_SCRIPT",
    "ssh_user": "META_SSH_USER",
    "ssh_host": "META_SSH_HOST",
    "ssh_port": "META_SSH_PORT",
    "remote_pid": "META_REMOTE_PID",
    "remote_pgid": "META_REMOTE_PGID",
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
    --lines)
      LINES="$2"
      shift 2
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
if [[ -z "${META_SSH_USER}" || -z "${META_SSH_HOST}" || -z "${META_SSH_PORT}" ]]; then
  echo "SSH connection info missing from metadata: ${META_SOURCE}" >&2
  exit 1
fi

SSH_TARGET="${META_SSH_USER}@${META_SSH_HOST}"
SSH_OPTS=(
  -o BatchMode=yes
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=10
  -o LogLevel=ERROR
  -p "${META_SSH_PORT}"
)

REMOTE_OUTPUT="$(
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" bash -s -- \
    "${META_REMOTE_PGID:-__EMPTY__}" \
    "${META_REMOTE_PID:-__EMPTY__}" \
    "${META_RUN_DIR}" \
    "${META_CONTROLLER_SCRIPT}" <<'REMOTE'
set -euo pipefail

REMOTE_PGID="$1"
REMOTE_PID="$2"
RUN_DIR="$3"
CONTROLLER_SCRIPT="$4"

if [[ "${REMOTE_PGID}" = "__EMPTY__" ]]; then
  REMOTE_PGID=""
fi
if [[ "${REMOTE_PID}" = "__EMPTY__" ]]; then
  REMOTE_PID=""
fi

CONTROLLER_LINE=""
ACTIVE_PGID=""
if [[ -n "${REMOTE_PID}" ]]; then
  CONTROLLER_LINE="$(
    ps -eo pid=,pgid=,stat=,etime=,cmd= | awk \
      -v pid="${REMOTE_PID}" \
      -v controller="${CONTROLLER_SCRIPT}" \
      '($1 == pid && index($0, "bash " controller) > 0) { print; exit }'
  )"
fi
if [[ -n "${CONTROLLER_LINE}" ]]; then
  ACTIVE_PGID="$(printf '%s\n' "${CONTROLLER_LINE}" | awk '{print $2}')"
fi

MATCHES="$(
  ps -eo pid=,pgid=,stat=,etime=,cmd= | awk \
    -v active_pgid="${ACTIVE_PGID}" \
    -v run_dir="${RUN_DIR}" \
    -v controller="${CONTROLLER_SCRIPT}" \
    '
      ((active_pgid != "" && $2 == active_pgid) ||
       index($0, "bash " controller) > 0 ||
       (index($0, "scripts/eval_reference_generation.py") > 0 && index($0, "--output-dir " run_dir) > 0) ||
       (index($0, "scripts/merge_reference_generation_results.py") > 0 && index($0, "--output-dir " run_dir) > 0)) {
        print
      }
    '
)"

if [[ -n "${MATCHES}" ]]; then
  echo "STATUS=running"
elif [[ -n "${REMOTE_PGID}" || -n "${REMOTE_PID}" ]]; then
  echo "STATUS=exited"
else
  echo "STATUS=unknown"
fi

echo "PROCESSES_BEGIN"
if [[ -n "${MATCHES}" ]]; then
  printf '%s\n' "${MATCHES}"
fi
echo "PROCESSES_END"
REMOTE
)"

REMOTE_STATUS="$(printf '%s\n' "${REMOTE_OUTPUT}" | sed -n 's/^STATUS=//p' | head -n 1)"
REMOTE_PROCESSES="$(
  printf '%s\n' "${REMOTE_OUTPUT}" | awk '
    /^PROCESSES_BEGIN$/ {capture=1; next}
    /^PROCESSES_END$/ {capture=0; next}
    capture {print}
  '
)"

SHARD_OUTPUT_COUNT="$(find "${META_RUN_DIR}" -maxdepth 1 -name 'per_sample.rank*.jsonl' | wc -l | tr -d ' ')"
SHARD_SUMMARY_COUNT="$(find "${META_RUN_DIR}" -maxdepth 1 -name 'summary.rank*.json' | wc -l | tr -d ' ')"
FINAL_SUMMARY="missing"
if [[ -f "${META_RUN_DIR}/summary.json" ]]; then
  FINAL_SUMMARY="present"
fi
if [[ "${REMOTE_STATUS}" = "unknown" && "${FINAL_SUMMARY}" = "present" ]]; then
  REMOTE_STATUS="exited"
fi

echo "Run dir: ${META_RUN_DIR}"
echo "Remote PID: ${META_REMOTE_PID:-unknown}"
echo "Remote PGID: ${META_REMOTE_PGID:-unknown}"
echo "Status: ${REMOTE_STATUS}"
echo "Shard outputs: ${SHARD_OUTPUT_COUNT}/${META_NUM_GPUS}"
echo "Shard summaries: ${SHARD_SUMMARY_COUNT}/${META_NUM_GPUS}"
echo "Merged summary: ${FINAL_SUMMARY}"

echo ""
echo "Remote processes:"
if [[ -n "${REMOTE_PROCESSES}" ]]; then
  printf '%s\n' "${REMOTE_PROCESSES}"
else
  echo "(none)"
fi

echo ""
echo "Controller log tail:"
if [[ -f "${META_CONTROLLER_LOG}" ]]; then
  tail -n "${LINES}" "${META_CONTROLLER_LOG}"
else
  echo "(controller log not found)"
fi
