#!/usr/bin/env python3
"""SemanticRecord 模型单元测试"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evokb.storage.models import SemanticRecord


def build_record(**overrides):
    data = {
        "repository": "test_repo",
        "relative_path": "src/test.c",
        "file_extension": ".c",
        "language": "C",
        "kind": "function",
        "node_type": "function_definition",
        "symbol_name": "foo",
        "qualified_name": "foo",
        "parent_qualified_name": None,
        "start_line": 10,
        "end_line": 20,
        "text": "int foo(void) {\n    return 1;\n}",
        "structure_fingerprint": None,
        "text_fingerprint": None,
        "created_at": None,
        "id": None,
    }
    data.update(overrides)
    return SemanticRecord(**data)


def test_semantic_record_creation():
    record = build_record()

    assert record.repository == "test_repo"
    assert record.kind == "function"
    assert record.qualified_name == "foo"
    assert record.start_line == 10
    assert record.end_line == 20
    assert record.text.startswith("int foo")
    assert record.structure_fingerprint is None
    assert record.text_fingerprint is None

    print("✓ test_semantic_record_creation passed")


def test_semantic_record_optional_fields():
    now = datetime.now()
    record = build_record(
        parent_qualified_name="Outer",
        structure_fingerprint="[1, 2, 3]",
        text_fingerprint="[4, 5, 6]",
        created_at=now,
        id=7,
    )

    assert record.parent_qualified_name == "Outer"
    assert record.structure_fingerprint == "[1, 2, 3]"
    assert record.text_fingerprint == "[4, 5, 6]"
    assert record.created_at == now
    assert record.id == 7

    print("✓ test_semantic_record_optional_fields passed")


def test_to_dict():
    record = build_record(kind="method", qualified_name="A::foo", parent_qualified_name="A")
    data = record.to_dict()

    assert data["kind"] == "method"
    assert data["qualified_name"] == "A::foo"
    assert data["parent_qualified_name"] == "A"
    assert data["start_line"] == 10
    assert "text_fingerprint" in data

    print("✓ test_to_dict passed")


def test_from_dict():
    data = build_record(kind="type", symbol_name="Node", qualified_name="Node").to_dict()
    record = SemanticRecord.from_dict(data)

    assert isinstance(record, SemanticRecord)
    assert record.kind == "type"
    assert record.symbol_name == "Node"
    assert record.qualified_name == "Node"

    print("✓ test_from_dict passed")


def test_round_trip_conversion():
    original = build_record(
        kind="global",
        symbol_name="VALUE",
        qualified_name="global::VALUE",
        text_fingerprint="[10, 20, 30]",
    )

    restored = SemanticRecord.from_dict(original.to_dict())

    assert restored.repository == original.repository
    assert restored.relative_path == original.relative_path
    assert restored.file_extension == original.file_extension
    assert restored.language == original.language
    assert restored.kind == original.kind
    assert restored.node_type == original.node_type
    assert restored.symbol_name == original.symbol_name
    assert restored.qualified_name == original.qualified_name
    assert restored.parent_qualified_name == original.parent_qualified_name
    assert restored.start_line == original.start_line
    assert restored.end_line == original.end_line
    assert restored.text == original.text
    assert restored.structure_fingerprint == original.structure_fingerprint
    assert restored.text_fingerprint == original.text_fingerprint
    assert restored.created_at == original.created_at
    assert restored.id == original.id

    print("✓ test_round_trip_conversion passed")


def test_empty_text_record():
    record = build_record(text="", start_line=1, end_line=1)

    assert record.text == ""
    assert record.start_line == 1
    assert record.end_line == 1

    print("✓ test_empty_text_record passed")


def main():
    print("Testing SemanticRecord...")
    print("=" * 60)

    try:
        test_semantic_record_creation()
        test_semantic_record_optional_fields()
        test_to_dict()
        test_from_dict()
        test_round_trip_conversion()
        test_empty_text_record()

        print("=" * 60)
        print("✓ All SemanticRecord tests passed!")
        return 0
    except AssertionError as exc:
        print("=" * 60)
        print(f"✗ Test failed: {exc}")
        return 1
    except Exception as exc:
        print("=" * 60)
        print(f"✗ Unexpected error: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
