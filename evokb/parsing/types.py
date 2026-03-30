from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Scope:
    name: str
    kind: str


@dataclass
class ParsedSemanticUnit:
    kind: str
    node_type: str
    symbol_name: str
    qualified_name: str
    parent_qualified_name: Optional[str]
    start_line: int
    end_line: int
    text: str
    start_byte: int
    end_byte: int
    ast_node: object = None
