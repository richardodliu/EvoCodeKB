import hashlib
from typing import List, Optional
from tree_sitter_language_pack import get_parser
from ..config.manager import TREE_SITTER_LANG_MAP

_COMMENT_NODE_TYPES = frozenset({"comment", "line_comment", "block_comment"})


class FingerprintTreeGenerator:
    """AST 指纹树生成器"""

    def __init__(self):
        self.parsers = {}
        self.lang_map = TREE_SITTER_LANG_MAP

    def get_parser(self, language: str):
        """获取解析器（带缓存）"""
        if language not in self.parsers:
            try:
                tree_sitter_lang = self.lang_map.get(language, language.lower())
                self.parsers[language] = get_parser(tree_sitter_lang)
            except Exception as e:
                print(f"警告: 无法加载 {language} 解析器: {e}")
                self.parsers[language] = None
        return self.parsers[language]

    def generate_fp_tree(self, code: str, language: str) -> Optional[List[int]]:
        """
        从代码文本生成指纹树（会重新解析）。

        用于检索阶段对查询代码生成指纹，以及无 AST 节点的 declaration_block 回退路径。
        """
        parser = self.get_parser(language)
        if parser is None:
            return None

        try:
            tree = parser.parse(code.encode('utf-8'))
            return self._traverse_node(tree.root_node)
        except Exception as e:
            print(f"警告: 生成指纹树失败: {e}")
            return None

    def generate_fp_from_node(self, node) -> Optional[List[int]]:
        """
        从已有的 tree-sitter AST 节点直接生成指纹树，避免重复解析。

        用于入库阶段——SemanticParser 已持有完整 AST，直接遍历子树即可。
        """
        try:
            return self._traverse_node(node)
        except Exception as e:
            print(f"警告: 从 AST 节点生成指纹树失败: {e}")
            return None

    def _traverse_node(self, root_node) -> List[int]:
        """迭代式后序遍历生成指纹树。"""
        fp_tree = []

        # stack 条目: (node, child_index)
        # result_stack: 每个已处理节点的指纹 hex 字符串（注释节点为 None）
        stack = [(root_node, 0)]
        result_stack = []

        while stack:
            node, child_idx = stack[-1]

            if node.type in _COMMENT_NODE_TYPES:
                stack.pop()
                result_stack.append(None)
                continue

            children = node.children
            if child_idx < len(children):
                stack[-1] = (node, child_idx + 1)
                stack.append((children[child_idx], 0))
            else:
                stack.pop()
                num_children = len(children)

                if num_children > 0:
                    fp = "0"
                    child_fps = result_stack[-num_children:]
                    del result_stack[-num_children:]
                    for child_fp in child_fps:
                        if child_fp is not None:
                            fp = self._hash_str(fp + child_fp)
                else:
                    fp = self._hash_str("0" + self._hash_str(node.type))

                fp_tree.append(int(fp[:16], 16))
                result_stack.append(fp)

        return fp_tree

    def _hash_str(self, s: str) -> str:
        """MD5 哈希字符串，返回16进制"""
        return hashlib.md5(s.encode()).hexdigest()
