from typing import Optional, Sequence, Tuple

from .constants import (
    FUNCTION_NODE_TYPES,
    GLOBAL_NODE_TYPES,
    NON_GLOBAL_ANCESTOR_TYPES,
    RECOVERED_INHERITANCE_LABEL_RE,
    RECOVERED_TYPE_PREFIX_RE,
    TYPE_LIKE_SYMBOL_NAMES,
    TYPE_NODE_TYPES,
)
from .names import NameExtractor, find_first_descendant, node_text
from .types import Scope


class SemanticClassifier:
    def __init__(self, names: NameExtractor):
        self.names = names

    def classify_node(
        self,
        node,
        language: str,
        scopes: Sequence[Scope],
        source_bytes: bytes,
    ) -> Optional[str]:
        if self.is_recovered_type_candidate(node, language, scopes, source_bytes):
            return "type"

        if node.type in TYPE_NODE_TYPES.get(language, set()):
            if self.is_redundant_nested_type(node, scopes, source_bytes):
                return None
            if self.is_type_definition_node(node, language):
                return "type"
            return None

        if node.type in FUNCTION_NODE_TYPES.get(language, set()):
            return "method" if self.has_type_scope(scopes) else "function"

        if self.is_recovered_function_candidate(node, language):
            return "method" if self.has_type_scope(scopes) else "function"

        if language == "Java" and node.type == "field_declaration":
            return "global"

        if node.type in GLOBAL_NODE_TYPES.get(language, set()):
            if self.has_executable_scope(scopes) or self.has_non_global_ancestor(
                node, language
            ):
                return None
            return "global"

        return None

    def is_semantic_candidate(self, node, language: str, source_bytes: bytes) -> bool:
        return (
            node.type in TYPE_NODE_TYPES.get(language, set())
            or node.type in FUNCTION_NODE_TYPES.get(language, set())
            or node.type in GLOBAL_NODE_TYPES.get(language, set())
            or self.is_recovered_type_candidate(node, language, [], source_bytes)
            or self.is_recovered_function_candidate(node, language)
        )

    def recover_unit_range(
        self,
        node,
        kind: Optional[str],
        language: str,
    ) -> Optional[Tuple[int, int]]:
        if kind not in {"function", "method"}:
            return None
        return self.recover_function_error_range(node, language)

    def should_skip_split_global_fragment(
        self,
        node,
        kind: str,
        symbol_name: str,
        normalized_end: int,
    ) -> bool:
        if kind != "global" or node.type != "declaration":
            return False
        if symbol_name not in TYPE_LIKE_SYMBOL_NAMES:
            return False

        sibling = node.next_named_sibling
        while sibling is not None:
            if sibling.start_byte >= normalized_end:
                return False
            if sibling.type == "declaration":
                return True
            sibling = sibling.next_named_sibling
        return False

    def has_type_scope(self, scopes: Sequence[Scope]) -> bool:
        return any(scope.kind == "type" for scope in scopes)

    def has_executable_scope(self, scopes: Sequence[Scope]) -> bool:
        return any(scope.kind in {"type", "function", "method"} for scope in scopes)

    def current_type_scope_name(self, scopes: Sequence[Scope]) -> Optional[str]:
        for scope in reversed(scopes):
            if scope.kind == "type":
                return scope.name
        return None

    def has_non_global_ancestor(self, node, language: str) -> bool:
        parent = node.parent
        blocked_types = NON_GLOBAL_ANCESTOR_TYPES.get(language, set())
        while parent is not None:
            if (
                parent.type in blocked_types
                or parent.type in FUNCTION_NODE_TYPES.get(language, set())
                or parent.type in TYPE_NODE_TYPES.get(language, set())
            ):
                return True
            parent = parent.parent
        return False

    def is_redundant_nested_type(
        self,
        node,
        scopes: Sequence[Scope],
        source_bytes: bytes,
    ) -> bool:
        current_type_name = self.current_type_scope_name(scopes)
        if not current_type_name:
            return False

        node_name = self.names.extract_type_name(node, source_bytes)
        if node_name != current_type_name:
            return False

        parent = node.parent
        return parent is not None and self.looks_like_keyword_prefixed_type(
            parent, source_bytes
        )

    def is_type_definition_node(self, node, language: str) -> bool:
        if language == "Java":
            return True

        child_types = {child.type for child in node.children if child.is_named}
        if node.type in {"struct_specifier", "class_specifier", "union_specifier"}:
            return "field_declaration_list" in child_types
        if node.type == "enum_specifier":
            return "enumerator_list" in child_types
        return True

    def is_recovered_type_candidate(
        self,
        node,
        language: str,
        scopes: Sequence[Scope],
        source_bytes: bytes,
    ) -> bool:
        if language != "C" or self.has_executable_scope(scopes):
            return False

        return self.looks_like_keyword_prefixed_type(
            node, source_bytes
        ) or self.looks_like_inheritance_labeled_type(node, source_bytes)

    def is_recovered_function_candidate(self, node, language: str) -> bool:
        return self.recover_function_error_range(node, language) is not None

    def recover_function_error_range(
        self,
        node,
        language: str,
    ) -> Optional[Tuple[int, int]]:
        if language != "C" or node.type != "ERROR":
            return None

        type_start = None
        identifier_seen = False
        open_paren_seen = False
        open_brace_index = None

        for index, child in enumerate(node.children):
            if child.is_named and self.is_type_like_child(child):
                if type_start is None:
                    type_start = child.start_byte
                continue

            if (
                child.is_named
                and child.type in {"identifier", "field_identifier"}
                and type_start is not None
            ):
                identifier_seen = True
                continue

            if child.type == "(" and identifier_seen:
                open_paren_seen = True
                continue

            if child.type == "{" and open_paren_seen:
                open_brace_index = index
                break

        if type_start is None or not identifier_seen or not open_paren_seen:
            return None
        if open_brace_index is None:
            return None

        has_body_content = any(
            child.is_named and child.type not in {"preproc_include"}
            for child in node.children[open_brace_index + 1 :]
        )
        if not has_body_content:
            return None

        return type_start, node.end_byte

    def is_type_like_child(self, node) -> bool:
        return node.type in {
            "primitive_type",
            "sized_type_specifier",
            "type_identifier",
            "qualified_identifier",
            "struct_specifier",
            "union_specifier",
            "enum_specifier",
            "storage_class_specifier",
            "type_qualifier",
        }

    def looks_like_keyword_prefixed_type(self, node, source_bytes: bytes) -> bool:
        if node.type != "function_definition":
            return False

        text = node_text(node, source_bytes).lstrip()
        if RECOVERED_TYPE_PREFIX_RE.match(text) is None:
            return False

        if self._has_function_declarator(node):
            return False

        has_body = any(
            child.is_named and child.type == "compound_statement" for child in node.children
        )
        has_name = self.names.extract_recovered_type_name(node, source_bytes) is not None
        return has_body and has_name

    def _has_function_declarator(self, node) -> bool:
        for child in node.children:
            if child.type == "function_declarator":
                return True
            if child.type in {"pointer_declarator", "reference_declarator"}:
                if self._has_function_declarator(child):
                    return True
        return False

    def looks_like_inheritance_labeled_type(self, node, source_bytes: bytes) -> bool:
        if node.type != "labeled_statement":
            return False

        text = node_text(node, source_bytes).lstrip()
        if RECOVERED_INHERITANCE_LABEL_RE.match(text) is None or "{" not in text:
            return False

        return any(
            child.is_named
            and child.type == "declaration"
            and find_first_descendant(child, {"initializer_list"}) is not None
            for child in node.children
        )
