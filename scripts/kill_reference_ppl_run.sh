#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS_BASE_DIR="${REPO_ROOT}/benchmark/runs/reference_ppl_qwen25coder7b"
LATEST_RUN_META="${RUNS_BASE_DIR}/latest_run.json"

RUN_DIR=""

usage() {
  cat <<'EOF'
Usage: bash scripts/kill_reference_ppl_run.sh [options]

Options:
  --run-dir PATH    Kill a specific run directory instead of latest
  --latest          Kill the latest submitted run (default)
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
    "controller_script": "META_CONTROLLER_SCRIPT",
    "ssh_user": "META_SSH_USER",
    "ssh_host": "META_SSH_HOST",
    "ssh_port": "META_SSH_PORT",
    "remote_pid": "META_REMOTE_PID",
    "remote_pgid": "META_REMOTE_PGID",
}
for key, env_name in mapping.items():
    value = meta.get(key)
    if value is None:
        value = ""
    print(f"{env_name}={shlex.quote(str(value))}")
PY
}

update_kill_meta() {
  KILLED_AT="${KILLED_AT}" \
  KILL_RESULT="${KILL_RESULT}" \
  KILL_FOUND_BEFORE="${KILL_FOUND_BEFORE}" \
  KILL_FOUND_AFTER="${KILL_FOUND_AFTER}" \
  RUN_DIR_VALUE="${META_RUN_DIR}" \
  RUN_META_PATH_VALUE="${META_RUN_META_PATH}" \
  LATEST_RUN_META_VALUE="${LATEST_RUN_META}" \
  python - <<'PY'
import json
import os
from pathlib import Path

targets = []
run_meta_path = Path(os.environ["RUN_META_PATH_VALUE"])
latest_meta_path = Path(os.environ["LATEST_RUN_META_VALUE"])

if run_meta_path.exists():
    targets.append(run_meta_path)
if latest_meta_path.exists():
    latest_data = json.loads(latest_meta_path.read_text(encoding="utf-8"))
    if latest_data.get("run_dir") == os.environ["RUN_DIR_VALUE"]:
        targets.append(latest_meta_path)

seen = set()
for target in targets:
    if target in seen:
        continue
    seen.add(target)
    data = json.loads(target.read_text(encoding="utf-8"))
    data["killed_at"] = os.environ["KILLED_AT"]
    data["kill_result"] = os.environ["KILL_RESULT"]
    data["kill_found_before"] = os.environ["KILL_FOUND_BEFORE"] == "1"
    data["kill_found_after"] = os.environ["KILL_FOUND_AFTER"] == "1"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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

echo "Killing run: ${META_RUN_DIR}"
echo "Remote target: ${SSH_TARGET}:${META_SSH_PORT}"

set +e
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

find_matches() {
  ps -eo pid=,pgid=,stat=,etime=,cmd= | awk \
    -v active_pgid="${ACTIVE_PGID}" \
    -v run_dir="${RUN_DIR}" \
    -v controller="${CONTROLLER_SCRIPT}" \
    '
      ((active_pgid != "" && $2 == active_pgid) ||
       index($0, "bash " controller) > 0 ||
       (index($0, "scripts/eval_reference_ppl.py") > 0 && index($0, "--output-dir " run_dir) > 0) ||
       (index($0, "scripts/merge_reference_ppl_results.py") > 0 && index($0, "--output-dir " run_dir) > 0)) {
        print
      }
    '
}

MATCHES_BEFORE="$(find_matches)"

echo "MATCHES_BEFORE_BEGIN"
if [[ -n "${MATCHES_BEFORE}" ]]; then
  printf '%s\n' "${MATCHES_BEFORE}"
fi
echo "MATCHES_BEFORE_END"

if [[ -z "${MATCHES_BEFORE}" ]]; then
  echo "KILL_RESULT=already_exited"
  echo "FOUND_BEFORE=0"
  echo "FOUND_AFTER=0"
  echo "MATCHES_AFTER_BEGIN"
  echo "MATCHES_AFTER_END"
  exit 0
fi

if [[ -n "${ACTIVE_PGID}" ]]; then
  kill -TERM -- "-${ACTIVE_PGID}" 2>/dev/null || true
fi
sleep 3

MATCHES_MID="$(find_matches)"
if [[ -n "${MATCHES_MID}" && -n "${ACTIVE_PGID}" ]]; then
  kill -KILL -- "-${ACTIVE_PGID}" 2>/dev/null || true
fi
sleep 1

FALLBACK_PIDS="$(find_matches | awk '{print $1}' | sort -u)"
if [[ -n "${FALLBACK_PIDS}" ]]; then
  while read -r target_pid; do
    if [[ -n "${target_pid}" ]]; then
      kill -TERM "${target_pid}" 2>/dev/null || true
    fi
  done <<< "${FALLBACK_PIDS}"
  sleep 1
fi

FALLBACK_PIDS="$(find_matches | awk '{print $1}' | sort -u)"
if [[ -n "${FALLBACK_PIDS}" ]]; then
  while read -r target_pid; do
    if [[ -n "${target_pid}" ]]; then
      kill -KILL "${target_pid}" 2>/dev/null || true
    fi
  done <<< "${FALLBACK_PIDS}"
  sleep 1
fi

MATCHES_AFTER="$(find_matches)"
echo "MATCHES_AFTER_BEGIN"
if [[ -n "${MATCHES_AFTER}" ]]; then
  printf '%s\n' "${MATCHES_AFTER}"
fi
echo "MATCHES_AFTER_END"

if [[ -n "${MATCHES_AFTER}" ]]; then
  echo "KILL_RESULT=still_running"
  echo "FOUND_BEFORE=1"
  echo "FOUND_AFTER=1"
  exit 1
fi

echo "KILL_RESULT=terminated"
echo "FOUND_BEFORE=1"
echo "FOUND_AFTER=0"
REMOTE
)"
SSH_EXIT="$?"
set -e

printf '%s\n' "${REMOTE_OUTPUT}"

KILL_RESULT="$(printf '%s\n' "${REMOTE_OUTPUT}" | sed -n 's/^KILL_RESULT=//p' | tail -n 1)"
KILL_FOUND_BEFORE="$(printf '%s\n' "${REMOTE_OUTPUT}" | sed -n 's/^FOUND_BEFORE=//p' | tail -n 1)"
KILL_FOUND_AFTER="$(printf '%s\n' "${REMOTE_OUTPUT}" | sed -n 's/^FOUND_AFTER=//p' | tail -n 1)"

if [[ -z "${KILL_RESULT}" ]]; then
  KILL_RESULT="remote_error"
fi
if [[ -z "${KILL_FOUND_BEFORE}" ]]; then
  KILL_FOUND_BEFORE="0"
fi
if [[ -z "${KILL_FOUND_AFTER}" ]]; then
  KILL_FOUND_AFTER="0"
fi

KILLED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
update_kill_meta

if [[ "${SSH_EXIT}" -ne 0 ]]; then
  echo "Remote kill reported leftover processes." >&2
  exit "${SSH_EXIT}"
fi

echo "Kill result: ${KILL_RESULT}"
