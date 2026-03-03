from pygments import lex
from pygments.lexers import get_lexer_by_name
from pygments.token import Token
from typing import Tuple

PYGMENTS_LANG_MAP = {
    'C': 'c',
    'C++': 'cpp',
    'Python': 'python',
    'Java': 'java',
}


class CodeParser:
    """使用 Pygments 进行代码解析"""

    def parse(self, content: str, language: str) -> Tuple[str, str]:
        """
        解析代码，分离代码和注释

        Args:
            content: 代码内容
            language: 语言类型

        Returns:
            (code, comment): 代码和注释的元组
        """
        try:
            lexer = self._get_lexer(language)
            tokens = list(lex(content, lexer))

            comments = []
            code_tokens = []

            for token_type, token_value in tokens:
                if token_type in Token.Comment:
                    comments.append(token_value)
                else:
                    code_tokens.append(token_value)

            return ''.join(code_tokens), ''.join(comments)

        except Exception as e:
            print(f"警告: Pygments 解析失败: {e}，使用简单方法")
            return content, ''

    def _get_lexer(self, language: str):
        """获取指定语言的 lexer"""
        name = PYGMENTS_LANG_MAP.get(language, 'text')
        return get_lexer_by_name(name)
