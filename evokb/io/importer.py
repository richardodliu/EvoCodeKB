from pathlib import Path
from typing import List
from ..storage.models import CodeRecord


class Importer:
    """批量导入器"""

    def __init__(self, knowledgebase):
        """
        Args:
            knowledgebase: KnowledgeBase 实例
        """
        self.kb = knowledgebase

    def import_directory(self, directory: str, repository: str = 'unknown'):
        """
        导入目录下的所有代码文件

        Args:
            directory: 目录路径
            repository: 仓库名
        """
        # 获取所有支持的扩展名
        extensions = list(self.kb.config_manager.ext_to_language.keys())

        # 获取所有文件
        files = self.kb.file_processor.get_files_by_extension(directory, extensions)

        print(f"找到 {len(files)} 个文件")

        success_count = 0
        error_count = 0

        for file_path in files:
            try:
                # 计算相对路径
                relative_path = str(Path(file_path).relative_to(directory))

                # 处理文件
                record = self.kb.process_file(file_path, repository, relative_path)
                self.kb.database.insert(record)

                success_count += 1
            except Exception as e:
                error_count += 1
                if error_count <= 3:
                    print(f"  错误: {file_path}: {e}")

        print(f"导入完成: 成功 {success_count}, 失败 {error_count}")
