from tree_sitter_language_pack import get_parser
from typing import Optional
from ..config.manager import TREE_SITTER_LANG_MAP


class SyntaxChecker:
    """使用 tree-sitter 进行语法检查"""

    def __init__(self):
        self.parsers = {}
        self.lang_map = TREE_SITTER_LANG_MAP

    def get_parser(self, language: str):
        """获取指定语言的解析器（带缓存）"""
        if language not in self.parsers:
            try:
                tree_sitter_lang = self.lang_map.get(language, language.lower())
                self.parsers[language] = get_parser(tree_sitter_lang)
            except Exception as e:
                print(f"警告: 无法加载 {language} 解析器: {e}")
                self.parsers[language] = None
        return self.parsers[language]

    def check_syntax(self, code: str, language: str) -> bool:
        """
        检查代码语法是否正确

        Args:
            code: 代码字符串
            language: 语言类型（如 'C'）

        Returns:
            bool: True 如果语法正确，False 如果有错误
        """
        parser = self.get_parser(language)
        if parser is None:
            return True  # 解析器不可用时跳过检查

        try:
            tree = parser.parse(code.encode('utf-8'))
            return not self._has_errors(tree.root_node)
        except Exception:
            return False

    def _has_errors(self, node) -> bool:
        """递归检查节点树中是否存在错误"""
        if node.type in ("ERROR", "MISSING"):
            return True
        for child in node.children:
            if self._has_errors(child):
                return True
        return False
