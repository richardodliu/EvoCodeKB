#!/usr/bin/env python3
"""SearchEngine 单元测试"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evokb.search.engine import SearchEngine
from evokb.storage.database import Database
from evokb.storage.models import SemanticRecord


def setup_test_db():
    return tempfile.mktemp(suffix=".db")


def cleanup_test_db(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)


def build_record(**overrides):
    data = {
        "repository": "repo1",
        "relative_path": "src/test.c",
        "file_extension": ".c",
        "language": "C",
        "kind": "function",
        "node_type": "function_definition",
        "symbol_name": "main",
        "qualified_name": "main",
        "parent_qualified_name": None,
        "start_line": 1,
        "end_line": 3,
        "text": 'int main() { printf("hello"); }',
        "structure_fingerprint": None,
        "text_fingerprint": None,
    }
    data.update(overrides)
    return SemanticRecord(**data)


def test_search_keyword():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        db.insert(build_record())
        db.insert(
            build_record(
                relative_path="src/value.c",
                kind="global",
                node_type="declaration",
                symbol_name="VALUE",
                qualified_name="global::VALUE",
                text="int VALUE = 42;",
            )
        )

        results = search_engine.search("main")
        assert len(results) == 1
        assert results[0]["qualified_name"] == "main"
        print("✓ test_search_keyword passed")
    finally:
        cleanup_test_db(db_path)


def test_search_empty_query():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        db.insert(build_record())
        db.insert(
            build_record(
                relative_path="src/other.c",
                symbol_name="foo",
                qualified_name="foo",
                text="int foo() { return 1; }",
            )
        )

        results = search_engine.search("")
        assert isinstance(results, list)
        assert len(results) == 2, f"空查询应匹配所有记录，实际 {len(results)}"
        print("✓ test_search_empty_query passed")
    finally:
        cleanup_test_db(db_path)


def test_search_special_characters():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        db.insert(build_record(text="100% complete"))
        db.insert(
            build_record(
                relative_path="src/other.c",
                symbol_name="under_score",
                qualified_name="under_score",
                text="int _value = 42;",
            )
        )

        results_percent = search_engine.search("%")
        assert len(results_percent) == 1, f"'%' 搜索应只匹配含 '%' 的记录，实际 {len(results_percent)}"
        assert "100% complete" in results_percent[0]["text"]

        results_underscore = search_engine.search("_value")
        assert len(results_underscore) == 1, f"'_value' 搜索应精确匹配，实际 {len(results_underscore)}"
        assert results_underscore[0]["symbol_name"] == "under_score"

        print("✓ test_search_special_characters passed")
    finally:
        cleanup_test_db(db_path)


def test_search_with_shots_limit():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        for i in range(5):
            db.insert(
                build_record(
                    relative_path=f"src/test{i}.c",
                    symbol_name=f"func{i}",
                    qualified_name=f"func{i}",
                    text=f"int func{i}() {{ return {i}; }}",
                )
            )

        results = search_engine.search("func", shots=3)
        assert len(results) == 3, f"shots=3 应返回 3 条，实际 {len(results)}"

        results_all = search_engine.search("func")
        assert len(results_all) == 5, f"无限制应返回全部 5 条，实际 {len(results_all)}"

        print("✓ test_search_with_shots_limit passed")
    finally:
        cleanup_test_db(db_path)


def test_search_with_repository_filter():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        db.insert(build_record(repository="repo1"))
        db.insert(build_record(repository="repo2", relative_path="src/other.c"))

        results = search_engine.search("main", repository="repo1")
        assert len(results) == 1
        assert results[0]["repository"] == "repo1"
        print("✓ test_search_with_repository_filter passed")
    finally:
        cleanup_test_db(db_path)


def test_search_with_language_and_kind_filter():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        db.insert(build_record(language="C", kind="function"))
        db.insert(
            build_record(
                relative_path="pkg/Test.java",
                file_extension=".java",
                language="Java",
                kind="type",
                node_type="class_declaration",
                symbol_name="Test",
                qualified_name="Test",
                text="class Test {\n    int value;\n}",
            )
        )

        results = search_engine.search("class", language="Java", kind="type")
        assert len(results) == 1
        assert results[0]["language"] == "Java"
        assert results[0]["kind"] == "type"
        print("✓ test_search_with_language_and_kind_filter passed")
    finally:
        cleanup_test_db(db_path)


def test_search_no_results():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)
        db.insert(build_record())

        results = search_engine.search("nonexistent_keyword_xyz")
        assert results == []
        print("✓ test_search_no_results passed")
    finally:
        cleanup_test_db(db_path)


def main():
    print("Testing SearchEngine...")
    print("=" * 60)

    try:
        test_search_keyword()
        test_search_empty_query()
        test_search_special_characters()
        test_search_with_shots_limit()
        test_search_with_repository_filter()
        test_search_with_language_and_kind_filter()
        test_search_no_results()

        print("=" * 60)
        print("✓ All SearchEngine tests passed!")
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
