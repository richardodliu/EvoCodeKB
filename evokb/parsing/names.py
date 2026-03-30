from typing import List, Optional, Sequence

from .constants import RECOVERED_TYPE_NAME_RE
from .types import Scope


NAME_TOKEN_TYPES = {
    "identifier",
    "field_identifier",
    "type_identifier",
    "namespace_identifier",
    "operator_name",
    "destructor_name",
}


def find_first_descendant(node, target_types: set):
    if node.type in target_types:
        return node
    for child in node.children:
        if child.is_named:
            result = find_first_descendant(child, target_types)
            if result is not None:
                return result
    return None


def node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def dedupe(items: Sequence[str]) -> List[str]:
    seen = set()
    ordered = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


class NameExtractor:
    def extract_symbol_name(
        self,
        node,
        kind: str,
        language: str,
        source_bytes: bytes,
    ) -> Optional[str]:
        if kind == "type":
            return self.extract_type_name(node, source_bytes)
        if kind in {"function", "method"}:
            return self.extract_function_name(node, language, source_bytes)
        if kind == "global":
            names = self.extract_global_names(node, language, source_bytes)
            return ",".join(names) if names else None
        return None

    def extract_type_name(self, node, source_bytes: bytes) -> Optional[str]:
        recovered_name = self.extract_recovered_type_name(node, source_bytes)
        if recovered_name is not None:
            return recovered_name

        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return node_text(name_node, source_bytes)

        for target_type in ("type_identifier", "identifier"):
            descendant = find_first_descendant(node, {target_type})
            if descendant is not None:
                return node_text(descendant, source_bytes)
        return None

    def extract_recovered_type_name(self, node, source_bytes: bytes) -> Optional[str]:
        if node.type == "labeled_statement":
            for child in node.children:
                if child.is_named and child.type in {
                    "statement_identifier",
                    "identifier",
                    "type_identifier",
                }:
                    return node_text(child, source_bytes)

        if node.type == "function_definition":
            named_children = [child for child in node.children if child.is_named]
            for index, child in enumerate(named_children):
                if child.type not in {"class_specifier", "struct_specifier", "union_specifier"}:
                    continue
                for follower in named_children[index + 1 :]:
                    if follower.type == "identifier":
                        return node_text(follower, source_bytes)
                break

            match = RECOVERED_TYPE_NAME_RE.match(node_text(node, source_bytes).lstrip())
            if match is not None:
                return match.group(1)

        return None

    def extract_function_name(self, node, language: str, source_bytes: bytes) -> Optional[str]:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return node_text(name_node, source_bytes)

        for child in node.children:
            if child.is_named and "declarator" in child.type:
                name = self.extract_declarator_name(child, source_bytes)
                if name:
                    return name

        return self.extract_declarator_name(node, source_bytes)

    def extract_global_names(self, node, language: str, source_bytes: bytes) -> List[str]:
        if node.type in {"type_definition", "alias_declaration"}:
            target = find_first_descendant(node, {"type_identifier", "identifier"})
            return [node_text(target, source_bytes)] if target is not None else []

        if node.type == "declaration":
            names = self.extract_c_like_declaration_names(node, source_bytes)
            return dedupe(names)

        if node.type in {"preproc_def", "preproc_function_def"}:
            name_node = node.child_by_field_name("name")
            return [node_text(name_node, source_bytes)] if name_node is not None else []

        if node.type == "field_declaration":
            names = []
            for child in node.children:
                if child.is_named and child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    if name_node is not None:
                        names.append(node_text(name_node, source_bytes))
            return dedupe(names)

        return []

    def extract_c_like_declaration_names(self, node, source_bytes: bytes) -> List[str]:
        names: List[str] = []
        named_children = [child for child in node.children if child.is_named]

        for index, child in enumerate(named_children):
            if child.type == "init_declarator":
                names.extend(self.collect_declaration_names(child, source_bytes))
                continue

            if child.type in {
                "function_declarator",
                "pointer_declarator",
                "reference_declarator",
                "array_declarator",
                "parenthesized_declarator",
                "qualified_identifier",
                "scoped_identifier",
                "identifier",
                "field_identifier",
                "operator_name",
                "destructor_name",
            }:
                name = self.extract_declarator_name(child, source_bytes)
                if name == "OF":
                    macro_name = self.extract_of_macro_name(named_children, index, source_bytes)
                    if macro_name:
                        names.append(macro_name)
                        continue
                if name:
                    names.append(name)

        return names

    def extract_of_macro_name(
        self,
        named_children: Sequence,
        current_index: int,
        source_bytes: bytes,
    ) -> Optional[str]:
        for child in reversed(named_children[:current_index]):
            if child.type in {
                "type_identifier",
                "identifier",
                "qualified_identifier",
                "scoped_identifier",
            }:
                return self.extract_declarator_name(child, source_bytes) or node_text(
                    child, source_bytes
                )
        return None

    def collect_declaration_names(self, node, source_bytes: bytes) -> List[str]:
        if node.type == "function_declarator":
            return []

        if node.type == "init_declarator":
            declarator = node.child_by_field_name("declarator")
            if declarator is not None:
                return self.collect_declaration_names(declarator, source_bytes)
            named_children = [child for child in node.children if child.is_named]
            if named_children:
                return self.collect_declaration_names(named_children[0], source_bytes)
            return []

        if node.type in {"identifier", "field_identifier"}:
            return [node_text(node, source_bytes)]

        names: List[str] = []
        for child in node.children:
            if child.is_named:
                names.extend(self.collect_declaration_names(child, source_bytes))
        return names

    def extract_declarator_name(self, node, source_bytes: bytes) -> Optional[str]:
        if node.type in NAME_TOKEN_TYPES:
            return node_text(node, source_bytes)

        if node.type in {"qualified_identifier", "scoped_identifier"}:
            tokens = self.collect_name_tokens(node, source_bytes)
            return tokens[-1] if tokens else None

        preferred_children = []
        fallback_children = []
        for child in node.children:
            if not child.is_named:
                continue
            if child.type in {
                "function_declarator",
                "pointer_declarator",
                "reference_declarator",
                "array_declarator",
                "parenthesized_declarator",
                "qualified_identifier",
                "scoped_identifier",
                "identifier",
                "field_identifier",
                "type_identifier",
                "operator_name",
                "destructor_name",
            }:
                preferred_children.append(child)
            else:
                fallback_children.append(child)

        for child in preferred_children + fallback_children:
            name = self.extract_declarator_name(child, source_bytes)
            if name:
                return name

        tokens = self.collect_name_tokens(node, source_bytes)
        return tokens[-1] if tokens else None

    def collect_name_tokens(self, node, source_bytes: bytes) -> List[str]:
        if node.type in NAME_TOKEN_TYPES:
            return [node_text(node, source_bytes)]

        tokens: List[str] = []
        for child in node.children:
            if child.is_named:
                tokens.extend(self.collect_name_tokens(child, source_bytes))
        return tokens

    def extract_namespace_name(self, node, source_bytes: bytes) -> Optional[str]:
        # C++17 nested namespace: namespace A::B::C { }
        for child in node.children:
            if child.type == "nested_namespace_specifier":
                tokens = self._collect_namespace_identifiers(child, source_bytes)
                return "::".join(tokens) if tokens else None

        # Simple namespace: namespace A { }
        target = find_first_descendant(node, {"namespace_identifier", "identifier"})
        return node_text(target, source_bytes) if target is not None else None

    def _collect_namespace_identifiers(
        self, node, source_bytes: bytes
    ) -> List[str]:
        result: List[str] = []
        for child in node.children:
            if child.type == "namespace_identifier":
                result.append(node_text(child, source_bytes))
            elif child.type == "nested_namespace_specifier":
                result.extend(
                    self._collect_namespace_identifiers(child, source_bytes)
                )
        return result

    def compose_parent_name(self, scopes: Sequence[Scope]) -> Optional[str]:
        names = [scope.name for scope in scopes if scope.name]
        return "::".join(names) if names else None

    def compose_qualified_name(
        self, parent_name: Optional[str], symbol_name: str, kind: str
    ) -> str:
        if kind == "global":
            return (
                f"{parent_name}::global::{symbol_name}"
                if parent_name
                else f"global::{symbol_name}"
            )
        return f"{parent_name}::{symbol_name}" if parent_name else symbol_name
