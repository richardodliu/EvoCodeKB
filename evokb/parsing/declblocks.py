from typing import List, Sequence

from .constants import LOCAL_DECLARATION_BLOCK_NODE_TYPES
from .ranges import RangeNormalizer
from .types import ParsedSemanticUnit


class DeclarationBlockBuilder:
    def __init__(self, ranges: RangeNormalizer):
        self.ranges = ranges

    def build_units(
        self,
        node,
        unit: ParsedSemanticUnit,
        language: str,
        source_bytes: bytes,
        line_offsets: Sequence[int],
    ) -> List[ParsedSemanticUnit]:
        if unit.kind not in {"function", "method"}:
            return []

        container = self.find_declaration_container(node)
        if container is None:
            return []

        declaration_types = LOCAL_DECLARATION_BLOCK_NODE_TYPES.get(language, {}).get(
            unit.kind, set()
        )
        if not declaration_types:
            return []

        blocks: List[ParsedSemanticUnit] = []
        current_nodes = []
        block_index = 1

        for child in container.children:
            if not child.is_named:
                continue
            if child.type == "comment" or child.type.startswith("preproc_"):
                continue

            if child.type in declaration_types:
                current_nodes.append(child)
                continue

            if current_nodes:
                block_unit = self.build_block_unit(
                    nodes=current_nodes,
                    unit=unit,
                    block_index=block_index,
                    language=language,
                    source_bytes=source_bytes,
                    line_offsets=line_offsets,
                )
                if block_unit is not None:
                    blocks.append(block_unit)
                block_index += 1
                current_nodes = []

        block_unit = self.build_block_unit(
            nodes=current_nodes,
            unit=unit,
            block_index=block_index,
            language=language,
            source_bytes=source_bytes,
            line_offsets=line_offsets,
        )
        if block_unit is not None:
            blocks.append(block_unit)

        return blocks

    def find_declaration_container(self, node):
        for child in node.children:
            if child.is_named and child.type in {"compound_statement", "block"}:
                return child
        return None

    def build_block_unit(
        self,
        nodes: Sequence,
        unit: ParsedSemanticUnit,
        block_index: int,
        language: str,
        source_bytes: bytes,
        line_offsets: Sequence[int],
    ):
        if not nodes:
            return None

        last_node_start = nodes[-1].start_byte
        _, last_node_end = self.ranges.normalize_unit_byte_range(
            node=nodes[-1],
            kind="declaration_block",
            language=language,
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            start_byte=last_node_start,
            end_byte=nodes[-1].end_byte,
        )
        materialized = self.ranges.materialize_range(
            source_bytes=source_bytes,
            line_offsets=line_offsets,
            start_byte=nodes[0].start_byte,
            end_byte=last_node_end,
            language=language,
            kind="declaration_block",
            include_leading_comments=False,
            semantic_count=len(nodes),
        )
        if materialized is None:
            return None

        start_byte, end_byte, start_line, end_line, text = materialized
        symbol_name = f"declblock#{block_index}"
        return ParsedSemanticUnit(
            kind="declaration_block",
            node_type="declaration_block",
            symbol_name=symbol_name,
            qualified_name=f"{unit.qualified_name}::{symbol_name}",
            parent_qualified_name=unit.qualified_name,
            start_line=start_line,
            end_line=end_line,
            text=text,
            start_byte=start_byte,
            end_byte=end_byte,
        )
