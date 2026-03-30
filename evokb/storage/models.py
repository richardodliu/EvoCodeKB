from dataclasses import dataclass, fields
from datetime import datetime
from typing import Optional


@dataclass
class SemanticRecord:
    """语义级条目数据模型。"""

    repository: str
    relative_path: str
    file_extension: str
    language: str
    kind: str
    node_type: str
    symbol_name: str
    qualified_name: str
    parent_qualified_name: Optional[str]
    start_line: int
    end_line: int
    text: str
    structure_fingerprint: Optional[str] = None
    text_fingerprint: Optional[str] = None
    created_at: Optional[datetime] = None
    id: Optional[int] = None

    def to_dict(self):
        """转换为字典。"""
        return {
            "repository": self.repository,
            "relative_path": self.relative_path,
            "file_extension": self.file_extension,
            "language": self.language,
            "kind": self.kind,
            "node_type": self.node_type,
            "symbol_name": self.symbol_name,
            "qualified_name": self.qualified_name,
            "parent_qualified_name": self.parent_qualified_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "text": self.text,
            "structure_fingerprint": self.structure_fingerprint,
            "text_fingerprint": self.text_fingerprint,
            "created_at": self.created_at,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建。"""
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)
