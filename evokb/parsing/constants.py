import re


TYPE_NODE_TYPES = {
    "C": {"class_specifier", "struct_specifier", "enum_specifier", "union_specifier"},
    "Java": {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "annotation_type_declaration",
        "record_declaration",
    },
}

FUNCTION_NODE_TYPES = {
    "C": {"function_definition"},
    "Java": {"method_declaration", "constructor_declaration"},
}

GLOBAL_NODE_TYPES = {
    "C": {"declaration", "type_definition", "alias_declaration", "preproc_def", "preproc_function_def"},
    "Java": set(),
}

LOCAL_DECLARATION_BLOCK_NODE_TYPES = {
    "C": {
        "function": {"declaration", "type_definition", "alias_declaration"},
        "method": {"declaration", "type_definition", "alias_declaration"},
    },
    "Java": {
        "method": {"local_variable_declaration"},
    },
}

NAMESPACE_NODE_TYPES = {
    "C": {"namespace_definition"},
}

COMMENT_PREFIXES = {
    "C": ("//", "/*", "* ", "*/"),
    "Java": ("//", "/*", "* ", "*/"),
}

WRAPPER_NODE_TYPES = {"decorated_definition", "template_declaration"}

NON_GLOBAL_ANCESTOR_TYPES = {
    "C": {
        "compound_statement",
        "for_statement",
        "if_statement",
        "while_statement",
        "switch_statement",
        "case_statement",
        "do_statement",
        "labeled_statement",
    },
    "Java": {
        "block",
        "class_body",
        "for_statement",
        "if_statement",
        "while_statement",
        "switch_block",
        "switch_block_statement_group",
    },
}

RECOVERED_TYPE_PREFIX_RE = re.compile(r"^(class|struct|union)\b")
RECOVERED_TYPE_NAME_RE = re.compile(
    r"^(?:class|struct|union)\b(?:\s+[A-Za-z_][A-Za-z0-9_]*)*\s+([A-Za-z_][A-Za-z0-9_]*)\b"
)
RECOVERED_INHERITANCE_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:<>]*\s*:\s*.+")

TYPE_LIKE_SYMBOL_NAMES = {
    "bool",
    "char",
    "double",
    "float",
    "int",
    "long",
    "short",
    "signed",
    "unsigned",
    "void",
    "_Bool",
}
