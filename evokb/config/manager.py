import json
from pathlib import Path
from typing import Dict, List


# Tree-sitter 语言映射（统一管理）
TREE_SITTER_LANG_MAP = {
    "C": "c",
    "C++": "cpp",
    "Python": "python",
    "Java": "java"
}

# 支持语法检查/指纹生成的语言列表
SUPPORTED_LANGUAGES = list(TREE_SITTER_LANG_MAP.keys())


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / 'config' / 'config.json'
        self.config_path = Path(config_path)
        self._ext_to_lang = None
        self._lang_config = None

    @property
    def ext_to_language(self) -> Dict[str, str]:
        """获取扩展名到语言的映射（懒加载）"""
        if self._ext_to_lang is None:
            self._load_config()
        return self._ext_to_lang

    @property
    def languages(self) -> List[dict]:
        """获取支持的语言列表"""
        if self._lang_config is None:
            self._load_config()
        return self._lang_config

    @property
    def tree_sitter_lang_map(self) -> Dict[str, str]:
        """获取 tree-sitter 语言映射"""
        return TREE_SITTER_LANG_MAP

    @property
    def supported_languages(self) -> List[str]:
        """获取支持语法检查/指纹生成的语言列表"""
        return SUPPORTED_LANGUAGES

    def _load_config(self):
        """加载配置文件"""
        with open(self.config_path, 'r') as f:
            config = json.load(f)

        self._lang_config = config['languages']
        self._ext_to_lang = {}
        for lang in self._lang_config:
            for ext in lang['extensions']:
                self._ext_to_lang[ext] = lang['name']

    def get_language(self, file_extension: str) -> str:
        """根据文件扩展名获取语言"""
        return self.ext_to_language.get(file_extension, 'unknown')
