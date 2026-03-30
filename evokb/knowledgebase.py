import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

from .config import ConfigManager
from .fingerprint import FingerprintTreeGenerator, TextFingerprintGenerator
from .io import FileProcessor, Importer
from .parsing import SemanticParser
from .retrieval import InformationRetrieval, KnowledgeRetrieval
from .search import SearchEngine
from .storage import Database, SemanticRecord


# --- 并行文件处理 worker ---

_worker_kb = None


def _init_file_worker(min_lines):
    """每个 worker 进程初始化独立的解析/指纹管线。"""
    global _worker_kb
    _worker_kb = KnowledgeBase.__new__(KnowledgeBase)
    _worker_kb.config_manager = ConfigManager()
    _worker_kb.semantic_parser = SemanticParser(min_lines=min_lines)
    _worker_kb.structure_fp_generator = FingerprintTreeGenerator()
    _worker_kb.text_fp_generator = TextFingerprintGenerator()
    _worker_kb.file_processor = FileProcessor(_worker_kb.config_manager)


def _run_file_worker(args):
    """worker 处理单个文件，返回 (records, error_msg)。"""
    content, file_path, repository, relative_path = args
    try:
        records = _worker_kb.process_file_from_content(
            content, file_path, repository, relative_path
        )
        return records, None
    except Exception as exc:
        return [], str(exc)[:80]


class KnowledgeBase:
    """代码知识库主协调器。"""

    def __init__(
        self,
        db_path: str = "code_kb.db",
        config_path: str = None,
        min_lines: int = 0,
    ):
        from . import ensure_runtime
        ensure_runtime()
        self.config_manager = ConfigManager(config_path)
        self.semantic_parser = SemanticParser(min_lines=min_lines)
        self.database = Database(db_path)
        self.search_engine = SearchEngine(self.database)
        self.file_processor = FileProcessor(self.config_manager)
        self.importer = Importer(self)
        self.structure_fp_generator = FingerprintTreeGenerator()
        self.text_fp_generator = TextFingerprintGenerator()
        self.knowledge_retrieval = KnowledgeRetrieval(
            self.database, self.structure_fp_generator
        )
        self.information_retrieval = InformationRetrieval(
            self.database, self.text_fp_generator
        )

    def process_file(
        self,
        file_path: str,
        repository: str = "unknown",
        relative_path: Optional[str] = None,
    ) -> List[SemanticRecord]:
        """读取并处理单个源码文件。"""
        content = self.file_processor.read_file(file_path)
        return self.process_file_from_content(content, file_path, repository, relative_path)

    def process_file_from_content(
        self,
        content: str,
        file_path: str,
        repository: str = "unknown",
        relative_path: Optional[str] = None,
    ) -> List[SemanticRecord]:
        """
        从给定源码内容中抽取语义条目。

        Returns:
            该文件生成的所有语义记录
        """
        file_extension = self.file_processor.get_extension(file_path)
        language = self.config_manager.get_language(file_extension)

        if language is None:
            return []

        if relative_path is None:
            relative_path = Path(file_path).name

        units = self.semantic_parser.parse(content, language)
        records: List[SemanticRecord] = []
        for unit in units:
            if unit.ast_node is not None:
                structure_fp = self.structure_fp_generator.generate_fp_from_node(unit.ast_node)
            else:
                structure_fp = self.structure_fp_generator.generate_fp_tree(unit.text, language)
            text_fp = self.text_fp_generator.generate(unit.text)

            records.append(
                SemanticRecord(
                    repository=repository,
                    relative_path=relative_path,
                    file_extension=file_extension,
                    language=language,
                    kind=unit.kind,
                    node_type=unit.node_type,
                    symbol_name=unit.symbol_name,
                    qualified_name=unit.qualified_name,
                    parent_qualified_name=unit.parent_qualified_name,
                    start_line=unit.start_line,
                    end_line=unit.end_line,
                    text=unit.text,
                    structure_fingerprint=json.dumps(structure_fp)
                    if structure_fp is not None
                    else None,
                    text_fingerprint=json.dumps(text_fp) if text_fp is not None else None,
                )
            )

        return records

    def update_database(
        self,
        file_path: str,
        repository: str = "unknown",
        relative_path: Optional[str] = None,
    ):
        """处理单个文件并将其所有语义条目写入数据库。"""
        records = self.process_file(file_path, repository, relative_path)
        self.database.insert_many(records)

    def process_files_parallel(
        self,
        file_tasks: List[tuple],
        max_workers: Optional[int] = None,
    ) -> tuple:
        """
        并行处理多个文件。

        Args:
            file_tasks: [(content, file_path, repository, relative_path), ...]
            max_workers: 进程数，默认 CPU 核心数（上限 8）

        Returns:
            (records, success_count, error_count, error_messages)
        """
        if max_workers is None:
            max_workers = min(os.cpu_count() or 1, 8)

        if max_workers <= 1 or len(file_tasks) <= 1:
            return self._process_files_serial(file_tasks)

        all_records = []
        success_count = 0
        error_count = 0
        error_messages = []

        min_lines = self.semantic_parser.ranges.min_lines
        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_init_file_worker,
            initargs=(min_lines,),
        ) as executor:
            for records, error in executor.map(
                _run_file_worker, file_tasks, chunksize=4
            ):
                all_records.extend(records)
                if error is None:
                    success_count += 1
                else:
                    error_count += 1
                    error_messages.append(error)

        return all_records, success_count, error_count, error_messages

    def _process_files_serial(self, file_tasks):
        """串行处理（回退路径）。"""
        all_records = []
        success_count = 0
        error_count = 0
        error_messages = []
        for content, file_path, repository, relative_path in file_tasks:
            try:
                records = self.process_file_from_content(
                    content, file_path, repository, relative_path
                )
                all_records.extend(records)
                success_count += 1
            except Exception as exc:
                error_count += 1
                error_messages.append(str(exc)[:80])
        return all_records, success_count, error_count, error_messages

    def update_database_from_records(self, records: List[SemanticRecord]):
        """批量写入语义条目。"""
        self.database.insert_many(records)

    def search_database(
        self,
        query: str,
        language: Optional[str] = None,
        repository: Optional[str] = None,
        kind: Optional[str] = None,
        shots: Optional[int] = None,
    ) -> List[Dict]:
        """按 text 字段检索语义条目。"""
        return self.search_engine.search(query, language, repository, kind, shots=shots)

    def get_stats(self) -> Dict:
        """获取数据库统计信息。"""
        return self.database.get_stats()

    def import_directory(self, directory: str, repository: str = "unknown"):
        """导入目录中的所有源码文件。"""
        self.importer.import_directory(directory, repository)

    def get_files_by_extension(self, directory: str, extensions: List[str]) -> List[str]:
        return self.file_processor.get_files_by_extension(directory, extensions)

    def knowledge_retrieve(
        self,
        input_code: str,
        language: str,
        shots: int = 5,
        repository: Optional[str] = None,
        limit: int = -1,
        max_candidates: int = -1,
    ) -> List[Dict]:
        return self.knowledge_retrieval.retrieve(
            input_code,
            language,
            shots,
            repository,
            limit=limit,
            max_candidates=max_candidates,
        )

    def knowledge_retrieve_many(
        self,
        input_codes: List[str],
        language: str,
        shots: int = 5,
        repository: Optional[str] = None,
        limit: int = -1,
        max_candidates: int = -1,
        max_workers: Optional[int] = None,
    ) -> List[List[Dict]]:
        return self.knowledge_retrieval.retrieve_many(
            input_codes,
            language,
            shots,
            repository,
            limit=limit,
            max_candidates=max_candidates,
            max_workers=max_workers,
        )

    def information_retrieve(
        self,
        input_text: str,
        language: Optional[str] = None,
        shots: int = 5,
        repository: Optional[str] = None,
        limit: int = -1,
        max_candidates: int = -1,
    ) -> List[Dict]:
        return self.information_retrieval.retrieve(
            input_text,
            language,
            shots,
            repository,
            limit=limit,
            max_candidates=max_candidates,
        )

    def information_retrieve_many(
        self,
        input_texts: List[str],
        language: Optional[str] = None,
        shots: int = 5,
        repository: Optional[str] = None,
        limit: int = -1,
        max_candidates: int = -1,
        max_workers: Optional[int] = None,
    ) -> List[List[Dict]]:
        return self.information_retrieval.retrieve_many(
            input_texts,
            language,
            shots,
            repository,
            limit=limit,
            max_candidates=max_candidates,
            max_workers=max_workers,
        )


def create_kb(db_path: str = "code_kb.db", min_lines: int = 0) -> KnowledgeBase:
    """向后兼容的工厂函数。"""
    return KnowledgeBase(db_path, min_lines=min_lines)
