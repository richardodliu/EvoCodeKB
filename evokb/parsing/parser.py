from typing import List, Optional, Sequence, Tuple

from tree_sitter_language_pack import get_parser

from ..config.manager import TREE_SITTER_LANG_MAP
from .classifier import SemanticClassifier
from .constants import NAMESPACE_NODE_TYPES, WRAPPER_NODE_TYPES
from .declblocks import DeclarationBlockBuilder
from .names import NameExtractor
from .ranges import RangeNormalizer
from .types import ParsedSemanticUnit, Scope


class SemanticParser:
    """使用 tree-sitter 抽取语义级代码条目。"""

    def __init__(self, min_lines: int = 0):
        self.parsers = {}
        self.lang_map = TREE_SITTER_LANG_MAP
        self.names = NameExtractor()
        self.ranges = RangeNormalizer(min_lines=min_lines)
        self.classifier = SemanticClassifier(self.names)
        self.declaration_blocks = DeclarationBlockBuilder(self.ranges)

    def get_parser(self, language: str):
        """获取指定语言的解析器（带缓存）。"""
        if language not in self.parsers:
            try:
                tree_sitter_lang = self.lang_map.get(language, language.lower())
                self.parsers[language] = get_parser(tree_sitter_lang)
            except Exception as exc:
                print(f"警告: 无法加载 {language} 解析器: {exc}")
                self.parsers[language] = None
        return self.parsers[language]

    def parse(self, content: str, language: str) -> List[ParsedSemanticUnit]:
        """从源码中提取语义级条目。"""
        if not content.strip():
            return []

        source_bytes = content.encode("utf-8")
        line_offsets = self.ranges.build_line_offsets(source_bytes)
        parser = self.get_parser(language)
        if parser is None:
            return []

        tree = parser.parse(source_bytes)
        units: List[ParsedSemanticUnit] = []
        self._visit(
            node=tree.root_node,
            language=language,
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            scopes=[],
            units=units,
            range_override=None,
        )
        units.sort(key=lambda item: (item.start_byte, -item.end_byte, item.qualified_name))
        return units

    def _visit(
        self,
        node,
        language: str,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        scopes: Sequence[Scope],
        units: List[ParsedSemanticUnit],
        range_override: Optional[Tuple[int, int]],
    ):
        if node.type in WRAPPER_NODE_TYPES:
            self._visit_wrapped_definition(
                node=node,
                language=language,
                source_bytes=source_bytes,
                line_offsets=line_offsets,
                scopes=scopes,
                units=units,
                range_override=range_override,
            )
            return

        if node.type in NAMESPACE_NODE_TYPES.get(language, set()):
            namespace_name = self.names.extract_namespace_name(node, source_bytes)
            next_scopes = list(scopes)
            if namespace_name:
                next_scopes.append(Scope(name=namespace_name, kind="namespace"))
            for child in node.children:
                if child.is_named:
                    self._visit(
                        node=child,
                        language=language,
                        source_bytes=source_bytes,
                        line_offsets=line_offsets,
                        scopes=next_scopes,
                        units=units,
                        range_override=None,
                    )
            return

        semantic_kind = self.classifier.classify_node(node, language, scopes, source_bytes)
        effective_range = range_override or self.classifier.recover_unit_range(
            node, semantic_kind, language
        )

        next_scopes = scopes
        if semantic_kind is not None:
            unit = self._build_unit(
                node=node,
                kind=semantic_kind,
                language=language,
                source_bytes=source_bytes,
                line_offsets=line_offsets,
                scopes=scopes,
                range_override=effective_range,
            )
            if unit is not None:
                units.append(unit)
                units.extend(
                    self._build_secondary_units(
                        node=node,
                        unit=unit,
                        language=language,
                        source_bytes=source_bytes,
                        line_offsets=line_offsets,
                    )
                )
                if unit.kind in {"type", "function", "method"}:
                    next_scopes = list(scopes)
                    next_scopes.append(Scope(name=unit.symbol_name, kind=unit.kind))

        for child in node.children:
            if child.is_named:
                self._visit(
                    node=child,
                    language=language,
                    source_bytes=source_bytes,
                    line_offsets=line_offsets,
                    scopes=next_scopes,
                    units=units,
                    range_override=None,
                )

    def _visit_wrapped_definition(
        self,
        node,
        language: str,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        scopes: Sequence[Scope],
        units: List[ParsedSemanticUnit],
        range_override: Optional[Tuple[int, int]],
    ):
        wrapper_range = range_override or (node.start_byte, node.end_byte)

        for child in node.children:
            if not child.is_named:
                continue
            if child.type in WRAPPER_NODE_TYPES or self.classifier.is_semantic_candidate(
                child, language, source_bytes
            ):
                self._visit(
                    node=child,
                    language=language,
                    source_bytes=source_bytes,
                    line_offsets=line_offsets,
                    scopes=scopes,
                    units=units,
                    range_override=wrapper_range,
                )
                return

        for child in node.children:
            if child.is_named:
                self._visit(
                    node=child,
                    language=language,
                    source_bytes=source_bytes,
                    line_offsets=line_offsets,
                    scopes=scopes,
                    units=units,
                    range_override=None,
                )

    def _build_unit(
        self,
        node,
        kind: str,
        language: str,
        source_bytes: bytes,
        line_offsets: Sequence[int],
        scopes: Sequence[Scope],
        range_override: Optional[Tuple[int, int]],
    ) -> Optional[ParsedSemanticUnit]:
        symbol_name = self.names.extract_symbol_name(node, kind, language, source_bytes)
        if not symbol_name:
            return None

        base_start = range_override[0] if range_override else node.start_byte
        base_end = range_override[1] if range_override else node.end_byte
        base_start, base_end = self.ranges.normalize_unit_byte_range(
            node=node,
            kind=kind,
            language=language,
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            start_byte=base_start,
            end_byte=base_end,
        )
        if self.classifier.should_skip_split_global_fragment(
            node=node,
            kind=kind,
            symbol_name=symbol_name,
            normalized_end=base_end,
        ):
            return None

        materialized = self.ranges.materialize_range(
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            start_byte=base_start,
            end_byte=base_end,
            language=language,
            kind=kind,
            include_leading_comments=True,
        )
        if materialized is None:
            return None

        start_byte, end_byte, start_line, end_line, text = materialized
        parent_name = self.names.compose_parent_name(scopes)
        qualified_name = self.names.compose_qualified_name(parent_name, symbol_name, kind)
        return ParsedSemanticUnit(
            kind=kind,
            node_type=node.type,
            symbol_name=symbol_name,
            qualified_name=qualified_name,
            parent_qualified_name=parent_name,
            start_line=start_line,
            end_line=end_line,
            text=text,
            start_byte=start_byte,
            end_byte=end_byte,
            ast_node=node,
        )

    def _build_secondary_units(
        self,
        node,
        unit: ParsedSemanticUnit,
        language: str,
        source_bytes: bytes,
        line_offsets: Sequence[int],
    ) -> List[ParsedSemanticUnit]:
        return self.declaration_blocks.build_units(
            node=node,
            unit=unit,
            language=language,
            source_bytes=source_bytes,
            line_offsets=line_offsets,
        )


CodeParser = SemanticParser
