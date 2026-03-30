#!/usr/bin/env python3
"""用 2-gram 指纹做信息检索（patch TextFingerprintGenerator 的 n 参数）。"""

import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from evokb.fingerprint.text_generator import TextFingerprintGenerator
import evokb.knowledgebase as kb_mod

# Patch KnowledgeBase 使用 n=2
_orig_init = kb_mod.KnowledgeBase.__init__

def _patched_init(self, *args, **kwargs):
    _orig_init(self, *args, **kwargs)
    self.text_fp_generator = TextFingerprintGenerator(n=2)
    self.information_retrieval.text_fp_generator = TextFingerprintGenerator(n=2)

kb_mod.KnowledgeBase.__init__ = _patched_init

# Patch worker initializer 使用 n=2
_orig_worker_init = kb_mod._init_file_worker

def _patched_worker_init(min_lines):
    _orig_worker_init(min_lines)
    kb_mod._worker_kb.text_fp_generator = TextFingerprintGenerator(n=2)

kb_mod._init_file_worker = _patched_worker_init

# 运行标准 retrieve_input
from scripts.retrieve_input import main
main()
