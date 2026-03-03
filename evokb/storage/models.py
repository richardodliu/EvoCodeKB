from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CodeRecord:
    """代码记录数据模型"""
    repository: str
    relative_path: str
    text: str
    code: str
    comment: str
    file_extension: str
    language: str
    code_fingerprint: Optional[str] = None
    comment_fingerprint: Optional[str] = None
    created_at: Optional[datetime] = None
    id: Optional[int] = None

    def to_dict(self):
        """转换为字典"""
        return {
            'repository': self.repository,
            'relative_path': self.relative_path,
            'text': self.text,
            'code': self.code,
            'comment': self.comment,
            'file_extension': self.file_extension,
            'language': self.language,
            'code_fingerprint': self.code_fingerprint,
            'comment_fingerprint': self.comment_fingerprint,
            'created_at': self.created_at,
            'id': self.id
        }

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建"""
        return cls(**data)
