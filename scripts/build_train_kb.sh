#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_ACTIVATE="/volume/pt-train/users/rbliu/miniconda3/bin/activate"
ENV_NAME="evokb"
DATA_DIR="${REPO_ROOT}/data/train"
DB_DIR="${REPO_ROOT}/knowledgebase"
DB_PATH="${DB_DIR}/train.db"

if [[ ! -f "${CONDA_ACTIVATE}" ]]; then
  echo "Conda activate script not found: ${CONDA_ACTIVATE}" >&2
  exit 1
fi

if [[ ! -d "${DATA_DIR}" ]]; then
  echo "Dataset directory not found: ${DATA_DIR}" >&2
  exit 1
fi

mkdir -p "${DB_DIR}"
rm -f "${DB_PATH}"

cd "${REPO_ROOT}"
source "${CONDA_ACTIVATE}" "${ENV_NAME}"

echo "Building knowledge base from ${DATA_DIR}"
echo "Output database: ${DB_PATH}"

python main.py update --knowledge_path "./data/train" --knowledge_base "train"
