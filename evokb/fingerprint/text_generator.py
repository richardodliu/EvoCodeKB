import re
import hashlib
from typing import List, Optional


class TextFingerprintGenerator:
    """文本 N-gram 指纹生成器。"""

    def __init__(self, n: int = 3):
        if n < 2:
            raise ValueError(f"n must be >= 2, got {n}")
        self.n = n

    def generate(self, text: str) -> Optional[List[int]]:
        """
        生成文本的 N-gram 指纹。

        Args:
            text: 输入文本

        Returns:
            List[int]: 指纹列表（整数哈希值），失败返回 None
        """
        if not text or not text.strip():
            return None

        words = re.findall(r"[a-zA-Z0-9_]+", text)
        if not words:
            return None

        n = self.n

        if len(words) < n:
            gram = " ".join(words)
            return [int(hashlib.md5(gram.encode()).hexdigest()[:16], 16)]

        grams = [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)]
        return [int(hashlib.md5(g.encode()).hexdigest()[:16], 16) for g in grams]
