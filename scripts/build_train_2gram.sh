#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_ACTIVATE="/volume/pt-train/users/rbliu/miniconda3/bin/activate"
ENV_NAME="evokb"
DATA_DIR="${REPO_ROOT}/data/train"
DB_DIR="${REPO_ROOT}/knowledgebase"
DB_PATH="${DB_DIR}/train_2gram.db"

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

echo "Building 2-gram knowledge base from ${DATA_DIR}"
echo "Output database: ${DB_PATH}"

python -c "
import sys
sys.path.insert(0, '.')
from evokb.fingerprint.text_generator import TextFingerprintGenerator
import evokb.knowledgebase as kb_mod

# Monkey-patch: 让 KnowledgeBase 和 worker 都使用 n=2
_orig_init = kb_mod.KnowledgeBase.__init__
def _patched_init(self, *args, **kwargs):
    _orig_init(self, *args, **kwargs)
    self.text_fp_generator = TextFingerprintGenerator(n=2)
kb_mod.KnowledgeBase.__init__ = _patched_init

_orig_worker_init = kb_mod._init_file_worker
def _patched_worker_init(min_lines):
    _orig_worker_init(min_lines)
    kb_mod._worker_kb.text_fp_generator = TextFingerprintGenerator(n=2)
kb_mod._init_file_worker = _patched_worker_init

from evokb.cli import main
sys.argv = ['evokb', 'update', '--knowledge_path', './data/train', '--knowledge_base', 'train_2gram']
main()
"
