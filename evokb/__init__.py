import os
import sys

__version__ = "0.1.0"

DEFAULT_RECURSION_LIMIT = int(os.environ.get("EVOKB_RECURSION_LIMIT", "20000"))


def configure_runtime(recursion_limit: int = DEFAULT_RECURSION_LIMIT) -> int:
    """确保运行时具备足够的递归深度。"""
    current_limit = sys.getrecursionlimit()
    if current_limit < recursion_limit:
        sys.setrecursionlimit(recursion_limit)
        current_limit = sys.getrecursionlimit()
    return current_limit


_runtime_configured = False


def ensure_runtime():
    """首次调用时配置运行时，后续调用跳过。"""
    global _runtime_configured
    if not _runtime_configured:
        configure_runtime()
        _runtime_configured = True


from .knowledgebase import KnowledgeBase, create_kb
from .config import ConfigManager
from .syntax import SyntaxChecker
from .parsing import CodeParser, SemanticParser
from .storage import Database, SemanticRecord
from .search import SearchEngine
from .io import FileProcessor, Importer
from .fingerprint import (
    FingerprintTreeGenerator,
    TextFingerprintGenerator,
)
from .retrieval import KnowledgeRetrieval, InformationRetrieval

__all__ = [
    'DEFAULT_RECURSION_LIMIT',
    'configure_runtime',
    'ensure_runtime',
    'KnowledgeBase',
    'create_kb',
    'ConfigManager',
    'SyntaxChecker',
    'SemanticParser',
    'CodeParser',
    'Database',
    'SemanticRecord',
    'SearchEngine',
    'FileProcessor',
    'Importer',
    'FingerprintTreeGenerator',
    'TextFingerprintGenerator',
    'KnowledgeRetrieval',
    'InformationRetrieval',
]
