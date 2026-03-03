from pathlib import Path
from typing import List
from ..config.manager import ConfigManager


class FileProcessor:
    """文件处理器"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager

    def read_file(self, file_path: str) -> str:
        """读取文件内容"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def get_files_by_extension(self, directory: str, extensions: List[str]) -> List[str]:
        """获取指定目录下所有满足后缀的文件"""
        directory_path = Path(directory)
        files = []
        for ext in extensions:
            files.extend(directory_path.rglob(f'*{ext}'))
        return [str(f) for f in files]

    def get_language(self, file_path: str) -> str:
        """根据文件路径获取语言"""
        file_extension = Path(file_path).suffix
        return self.config_manager.get_language(file_extension)

    def get_extension(self, file_path: str) -> str:
        """获取文件扩展名"""
        return Path(file_path).suffix
