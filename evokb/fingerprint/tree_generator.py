import hashlib
import re
import tokenize
from io import StringIO
from typing import List, Optional
from tree_sitter_language_pack import get_parser
from ..config.manager import TREE_SITTER_LANG_MAP


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
        生成代码的指纹树

        Args:
            code: 代码字符串
            language: 语言类型

        Returns:
            List[int]: 指纹树（整数哈希值列表），失败返回 None
        """
        parser = self.get_parser(language)
        if parser is None:
            return None

        try:
            code = self._remove_comments(code, language)
        except Exception:
            pass

        try:
            tree = parser.parse(code.encode('utf-8'))
            root_node = tree.root_node

            fp_tree = []

            def fingerprint_tree(node):
                """后序遍历生成指纹"""
                fp = "0"
                if len(node.children) > 0:
                    for child in node.children:
                        fp = self._hash_str(fp + str(fingerprint_tree(child)))
                else:
                    fp = self._hash_str(fp + self._hash_str(node.type))

                fp_tree.append(int(fp, 16))
                return fp

            fingerprint_tree(root_node)
            return fp_tree

        except Exception as e:
            print(f"警告: 生成指纹树失败: {e}")
            return None

    def _hash_str(self, s: str) -> str:
        """MD5 哈希字符串，返回16进制"""
        return hashlib.md5(s.encode()).hexdigest()

    def _remove_comments(self, source: str, language: str) -> str:
        """剥离注释和文档字符串"""
        if language == 'Python':
            io_obj = StringIO(source)
            out = ""
            prev_toktype = tokenize.INDENT
            last_lineno = -1
            last_col = 0
            for tok in tokenize.generate_tokens(io_obj.readline):
                token_type = tok[0]
                token_string = tok[1]
                start_line, start_col = tok[2]
                end_line, end_col = tok[3]
                if start_line > last_lineno:
                    last_col = 0
                if start_col > last_col:
                    out += (" " * (start_col - last_col))
                if token_type == tokenize.COMMENT:
                    pass
                elif token_type == tokenize.STRING:
                    if prev_toktype != tokenize.INDENT:
                        if prev_toktype != tokenize.NEWLINE:
                            if start_col > 0:
                                out += token_string
                else:
                    out += token_string
                prev_toktype = token_type
                last_col = end_col
                last_lineno = end_line
            return '\n'.join(x for x in out.split('\n') if x.strip())
        elif language in ('C', 'C++', 'Java'):
            def replacer(match):
                s = match.group(0)
                if s.startswith('/'):
                    return " "
                return s
            pattern = re.compile(
                r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
                re.DOTALL | re.MULTILINE
            )
            return '\n'.join(x for x in re.sub(pattern, replacer, source).split('\n') if x.strip())
        else:
            return source
