#!/usr/bin/env python3
"""Database 单元测试"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
        "symbol_name": "foo",
        "qualified_name": "foo",
        "parent_qualified_name": None,
        "start_line": 3,
        "end_line": 5,
        "text": "int foo(void) { return 1; }",
        "structure_fingerprint": "[1, 2, 3]",
        "text_fingerprint": "[4, 5, 6]",
    }
    data.update(overrides)
    return SemanticRecord(**data)


def test_database_initialization():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        assert os.path.exists(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='code_knowledge'"
        )
        assert cursor.fetchone() is not None
        conn.close()
        print("✓ test_database_initialization passed")
    finally:
        cleanup_test_db(db_path)


def test_insert_and_query_record():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        record = build_record()
        db.insert(record)

        results = db.query()
        assert len(results) == 1
        assert results[0].qualified_name == "foo"
        assert results[0].structure_fingerprint == "[1, 2, 3]"
        assert results[0].text_fingerprint == "[4, 5, 6]"
        print("✓ test_insert_and_query_record passed")
    finally:
        cleanup_test_db(db_path)


def test_insert_duplicate_replaces():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        db.insert(build_record(text="old"))
        db.insert(build_record(text="new"))

        results = db.query()
        assert len(results) == 1
        assert results[0].text == "new"
        print("✓ test_insert_duplicate_replaces passed")
    finally:
        cleanup_test_db(db_path)


def test_query_filters():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        db.insert(build_record(repository="repo1", language="C", kind="function"))
        db.insert(
            build_record(
                repository="repo2",
                relative_path="pkg/Test.java",
                file_extension=".java",
                language="Java",
                kind="type",
                node_type="class_declaration",
                symbol_name="Test",
                qualified_name="Test",
            )
        )

        assert len(db.query(language="C")) == 1
        assert len(db.query(repository="repo2")) == 1
        assert len(db.query(kind="type")) == 1
        print("✓ test_query_filters passed")
    finally:
        cleanup_test_db(db_path)


def test_get_stats():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        db.insert(build_record(kind="function"))
        db.insert(
            build_record(
                relative_path="src/test2.c",
                symbol_name="Node",
                qualified_name="Node",
                kind="type",
                node_type="struct_specifier",
            )
        )

        stats = db.get_stats()
        assert stats["total_entries"] == 2
        assert stats["by_language"]["C"] == 2
        assert stats["by_repository"]["repo1"] == 2
        assert stats["by_kind"]["function"] == 1
        assert stats["by_kind"]["type"] == 1
        print("✓ test_get_stats passed")
    finally:
        cleanup_test_db(db_path)


def test_search_text():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        db.insert(build_record(text="int foo(void) { return 1; }"))
        db.insert(build_record(relative_path="x.c", qualified_name="global::VALUE", symbol_name="VALUE", kind="global", text="VALUE = 1"))

        results = db.search("foo", kind="function")
        assert len(results) == 1
        assert results[0].qualified_name == "foo"
        print("✓ test_search_text passed")
    finally:
        cleanup_test_db(db_path)


def test_query_fingerprints():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        db.insert(build_record())

        rows = db.query_fingerprints()
        assert len(rows) == 1
        assert rows[0]["qualified_name"] == "foo"
        assert rows[0]["structure_fingerprint"] == "[1, 2, 3]"
        assert rows[0]["text_fingerprint"] == "[4, 5, 6]"
        print("✓ test_query_fingerprints passed")
    finally:
        cleanup_test_db(db_path)


def test_insert_many_batch():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        records = [
            build_record(
                relative_path=f"src/test{i}.c",
                symbol_name=f"func{i}",
                qualified_name=f"func{i}",
            )
            for i in range(5)
        ]
        db.insert_many(records)

        results = db.query()
        assert len(results) == 5, f"批量插入 5 条，实际 {len(results)}"
        names = {r.qualified_name for r in results}
        assert names == {f"func{i}" for i in range(5)}

        # 验证批量时间戳一致
        timestamps = {r.created_at for r in results}
        assert len(timestamps) == 1, f"同批次记录应有相同时间戳，实际 {len(timestamps)} 个不同值"

        print("✓ test_insert_many_batch passed")
    finally:
        cleanup_test_db(db_path)


def test_insert_many_empty():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        db.insert_many([])
        assert db.query() == []
        print("✓ test_insert_many_empty passed")
    finally:
        cleanup_test_db(db_path)


def test_query_by_ids():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        records = [
            build_record(
                relative_path=f"src/test{i}.c",
                symbol_name=f"func{i}",
                qualified_name=f"func{i}",
            )
            for i in range(3)
        ]
        db.insert_many(records)

        all_records = db.query()
        ids = [r.id for r in all_records]

        # 查询部分 id
        subset = db.query_by_ids(ids[:2])
        assert len(subset) == 2, f"查询 2 个 id 应返回 2 条，实际 {len(subset)}"
        subset_names = {r.qualified_name for r in subset}
        expected_names = {all_records[0].qualified_name, all_records[1].qualified_name}
        assert subset_names == expected_names

        # 空 id 列表
        assert db.query_by_ids([]) == []

        # 不存在的 id
        assert db.query_by_ids([99999]) == []

        print("✓ test_query_by_ids passed")
    finally:
        cleanup_test_db(db_path)


def test_query_retrieval_candidates_basic():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        db.insert(build_record())

        rows = db.query_retrieval_candidates()
        assert len(rows) == 1
        assert rows[0]["qualified_name"] == "foo"
        assert rows[0]["structure_fingerprint"] == "[1, 2, 3]"
        assert rows[0]["text_fingerprint"] == "[4, 5, 6]"
        assert "text" not in rows[0], "默认不应包含 text 列"

        print("✓ test_query_retrieval_candidates_basic passed")
    finally:
        cleanup_test_db(db_path)


def test_query_retrieval_candidates_include_text():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        db.insert(build_record())

        rows = db.query_retrieval_candidates(include_text=True)
        assert len(rows) == 1
        assert "text" in rows[0], "include_text=True 应包含 text 列"
        assert rows[0]["text"] == "int foo(void) { return 1; }"

        print("✓ test_query_retrieval_candidates_include_text passed")
    finally:
        cleanup_test_db(db_path)


def test_query_retrieval_candidates_language_filter():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        db.insert(build_record(language="C"))
        db.insert(
            build_record(
                relative_path="pkg/Test.java",
                file_extension=".java",
                language="Java",
                symbol_name="Test",
                qualified_name="Test",
            )
        )

        # 单语言字符串
        rows_c = db.query_retrieval_candidates(language="C")
        assert len(rows_c) == 1
        assert rows_c[0]["language"] == "C"

        # 多语言元组 (IN 子句)
        rows_both = db.query_retrieval_candidates(language=("C", "Java"))
        assert len(rows_both) == 2

        # 不存在的语言
        rows_none = db.query_retrieval_candidates(language="Python")
        assert len(rows_none) == 0

        print("✓ test_query_retrieval_candidates_language_filter passed")
    finally:
        cleanup_test_db(db_path)


def test_query_with_limit():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        for i in range(5):
            db.insert(
                build_record(
                    relative_path=f"src/test{i}.c",
                    symbol_name=f"func{i}",
                    qualified_name=f"func{i}",
                )
            )

        results = db.query(limit=3)
        assert len(results) == 3, f"limit=3 应返回 3 条，实际 {len(results)}"

        results_all = db.query()
        assert len(results_all) == 5

        # limit=0 和 limit=-1 不应限制
        results_zero = db.query(limit=0)
        assert len(results_zero) == 5
        results_neg = db.query(limit=-1)
        assert len(results_neg) == 5

        print("✓ test_query_with_limit passed")
    finally:
        cleanup_test_db(db_path)


def main():
    print("Testing Database...")
    print("=" * 60)

    try:
        test_database_initialization()
        test_insert_and_query_record()
        test_insert_duplicate_replaces()
        test_query_filters()
        test_get_stats()
        test_search_text()
        test_query_fingerprints()
        test_insert_many_batch()
        test_insert_many_empty()
        test_query_by_ids()
        test_query_retrieval_candidates_basic()
        test_query_retrieval_candidates_include_text()
        test_query_retrieval_candidates_language_filter()
        test_query_with_limit()

        print("=" * 60)
        print("✓ All Database tests passed!")
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
