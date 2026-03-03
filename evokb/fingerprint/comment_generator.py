import re
import hashlib
from typing import List, Optional


class CommentFingerprintGenerator:
    """注释 N-gram 指纹生成器"""

    def __init__(self, n: int = 5):
        self.n = n

    def generate(self, comment: str) -> Optional[List[int]]:
        """
        生成注释的 N-gram 指纹

        Args:
            comment: 注释字符串

        Returns:
            List[int]: 指纹列表（整数哈希值），失败返回 None
        """
        if not comment or not comment.strip():
            return None

        # 去掉符号，只保留单词（字母、数字、下划线）
        words = re.findall(r'[a-zA-Z0-9_]+', comment)
        if not words:
            return None

        n = self.n

        # 词数不足 n 时，将全部单词拼接为一个 gram
        if len(words) < n:
            gram = ' '.join(words)
            return [int(hashlib.md5(gram.encode()).hexdigest(), 16)]

        grams = [' '.join(words[i:i + n]) for i in range(len(words) - n + 1)]
        return [int(hashlib.md5(g.encode()).hexdigest(), 16) for g in grams]
