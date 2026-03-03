from pathlib import Path
from typing import Optional, List, Dict
import json
from .config import ConfigManager
from .syntax import SyntaxChecker
from .parsing import CodeParser
from .storage import Database, CodeRecord
from .search import SearchEngine
from .io import FileProcessor, Importer
from .fingerprint import FingerprintTreeGenerator, CommentFingerprintGenerator
from .retrieval import KnowledgeRetrieval, InformationRetrieval


class KnowledgeBase:
    """代码知识库 - 主协调器"""

    def __init__(self, db_path: str = 'code_kb.db', config_path: str = None):
        """
        初始化知识库

        Args:
            db_path: 数据库路径
            config_path: 配置文件路径
        """
        self.config_manager = ConfigManager(config_path)
        self.syntax_checker = SyntaxChecker()
        self.code_parser = CodeParser()
        self.database = Database(db_path)
        self.search_engine = SearchEngine(self.database)
        self.file_processor = FileProcessor(self.config_manager)
        self.importer = Importer(self)
        self.code_fp_generator = FingerprintTreeGenerator()
        self.comment_fp_generator = CommentFingerprintGenerator()
        self.knowledge_retrieval = KnowledgeRetrieval(self.database, self.code_fp_generator)
        self.information_retrieval = InformationRetrieval(self.database, self.comment_fp_generator)

    def process_file(self, file_path: str, repository: str = 'unknown',
                     relative_path: Optional[str] = None) -> CodeRecord:
        """
        处理单个代码文件

        Args:
            file_path: 文件路径
            repository: 仓库名
            relative_path: 相对路径

        Returns:
            CodeRecord: 处理后的代码记录
        """
        content = self.file_processor.read_file(file_path)
        return self.process_file_from_content(content, file_path, repository, relative_path)

    def process_file_from_content(self, content: str, file_path: str,
                                   repository: str = 'unknown',
                                   relative_path: Optional[str] = None) -> CodeRecord:
        """
        从文件内容处理（不从磁盘读取）

        Args:
            content: 文件内容字符串
            file_path: 文件路径（用于推断语言）
            repository: 仓库名
            relative_path: 相对路径

        Returns:
            CodeRecord: 处理后的代码记录
        """
        text = content
        file_extension = self.file_processor.get_extension(file_path)
        language = self.config_manager.get_language(file_extension)

        # 语法检查（仅对支持的语言）
        if language in self.config_manager.supported_languages:
            if not self.syntax_checker.check_syntax(text, language):
                raise SyntaxError(f"{language} 语法错误")

        # 使用 Pygments 进行词法分析
        code, comment = self.code_parser.parse(text, language)

        # 如果没有提供相对路径，使用文件名
        if relative_path is None:
            relative_path = Path(file_path).name

        # 生成指纹树
        fp_tree = self.code_fp_generator.generate_fp_tree(text, language)
        code_fingerprint_json = json.dumps(fp_tree) if fp_tree else None

        # 生成注释指纹
        comment_fp = self.comment_fp_generator.generate(comment)
        comment_fingerprint_json = json.dumps(comment_fp) if comment_fp else None

        return CodeRecord(
            repository=repository,
            relative_path=relative_path,
            text=text,
            code=code,
            comment=comment,
            file_extension=file_extension,
            language=language,
            code_fingerprint=code_fingerprint_json,
            comment_fingerprint=comment_fingerprint_json
        )

    def update_database(self, file_path: str, repository: str = 'unknown',
                       relative_path: Optional[str] = None):
        """
        更新数据库：给定一个代码文件，提取代码和注释并保存

        Args:
            file_path: 文件路径
            repository: 仓库名
            relative_path: 相对路径
        """
        record = self.process_file(file_path, repository, relative_path)
        self.database.insert(record)

    def update_database_from_dict(self, data):
        """
        从字典或 CodeRecord 更新数据库

        Args:
            data: 字典或 CodeRecord 对象
        """
        if isinstance(data, CodeRecord):
            record = data
        else:
            record = CodeRecord(
                repository=data['repository'],
                relative_path=data['relative_path'],
                text=data['text'],
                code=data['code'],
                comment=data['comment'],
                file_extension=data['file_extension'],
                language=data['language'],
                code_fingerprint=data.get('code_fingerprint'),
                comment_fingerprint=data.get('comment_fingerprint')
            )
        self.database.insert(record)

    def search_database(self, query: str, search_type: str = 'all',
                        language: Optional[str] = None,
                        repository: Optional[str] = None) -> List[Dict]:
        """
        检索数据库

        Args:
            query: 搜索关键词
            search_type: 'all' | 'code' | 'comment' | 'text'
            language: 按语言过滤
            repository: 按仓库过滤

        Returns:
            匹配的记录列表
        """
        return self.search_engine.search(query, search_type, language, repository)

    def get_stats(self) -> Dict:
        """获取数据库统计信息"""
        return self.database.get_stats()

    def import_directory(self, directory: str, repository: str = 'unknown'):
        """
        导入目录下的所有代码文件

        Args:
            directory: 目录路径
            repository: 仓库名
        """
        self.importer.import_directory(directory, repository)

    def get_files_by_extension(self, directory: str, extensions: List[str]) -> List[str]:
        """获取指定目录下所有满足后缀的文件"""
        return self.file_processor.get_files_by_extension(directory, extensions)

    def knowledge_retrieve(self,
                           input_code: str,
                           language: str,
                           shots: int = 5,
                           repository: Optional[str] = None,
                           limit: int = -1) -> List[Dict]:
        """
        检索与输入代码相似的代码片段

        Args:
            input_code: 输入代码
            language: 语言类型
            shots: 返回的代码数量
            repository: 可选，限定仓库
            limit: 预过滤候选数量，-1 表示不过滤

        Returns:
            List[Dict]: 检索到的代码记录列表
        """
        return self.knowledge_retrieval.retrieve(input_code, language, shots,
                                                    repository,
                                                    limit=limit)

    def information_retrieve(self,
                             input_text: str,
                             language: Optional[str] = None,
                             shots: int = 5,
                             repository: Optional[str] = None,
                             limit: int = -1) -> List[Dict]:
        """
        基于注释指纹检索与输入文本最相关的代码片段

        Args:
            input_text: 输入文本（自然语言描述）
            language: 可选，按语言过滤
            shots: 返回的代码数量
            repository: 可选，限定仓库
            limit: 预过滤候选数量，-1 表示不过滤

        Returns:
            List[Dict]: 检索到的代码记录列表
        """
        return self.information_retrieval.retrieve(
            input_text, language, shots, repository, limit=limit)


# 工厂函数（向后兼容）
def create_kb(db_path: str = 'code_kb.db') -> KnowledgeBase:
    """创建知识库实例"""
    return KnowledgeBase(db_path)
