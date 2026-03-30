#!/usr/bin/env python3
"""知识/信息检索集成测试"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evokb.knowledgebase import KnowledgeBase


TEST_DB_PATH = tempfile.mktemp(suffix=".db", prefix="test_retrieval_")


def cleanup():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def test_fingerprint_generation():
    cleanup()
    try:
        kb = KnowledgeBase(TEST_DB_PATH, min_lines=0)
        test_code = """
#include <stdio.h>

/* print a value */
int print_value(int x) {
    printf("%d\\n", x);
    return x;
}
"""

        records = kb.process_file_from_content(
            content=test_code,
            file_path="test.c",
            repository="test_repo",
            relative_path="test.c",
        )

        assert records, "应生成语义条目"
        function_record = next(record for record in records if record.kind == "function")
        assert function_record.structure_fingerprint, "结构指纹生成失败"
        assert function_record.text_fingerprint, "文本指纹生成失败"
        print("✓ test_fingerprint_generation passed")
    finally:
        cleanup()


def test_database_storage():
    cleanup()
    try:
        kb = KnowledgeBase(TEST_DB_PATH, min_lines=0)
        snippets = [
            ("#include <stdio.h>\nint hello() { return 1; }\n", "hello.c", "test1"),
            ("class A {\n    int m() { return 1; }\n}\n", "A.java", "test2"),
        ]

        total_records = 0
        for content, file_path, repo in snippets:
            records = kb.process_file_from_content(content, file_path, repo, file_path)
            kb.update_database_from_records(records)
            total_records += len(records)

        results = kb.database.query()
        assert len(results) == total_records
        assert any(record.kind == "function" for record in results)
        assert any(record.kind == "type" for record in results)
        print("✓ test_database_storage passed")
    finally:
        cleanup()


def test_knowledge_retrieval():
    cleanup()
    try:
        kb = KnowledgeBase(TEST_DB_PATH, min_lines=0)
        snippets = [
            ("int hello() { return 1; }\n", "hello.c", "test1"),
            ("int add(int a, int b) { return a + b; }\n", "add.c", "test2"),
            ("int mul(int a, int b) { return a * b; }\n", "mul.c", "test3"),
        ]

        for content, file_path, repo in snippets:
            records = kb.process_file_from_content(content, file_path, repo, file_path)
            kb.update_database_from_records(records)

        results = kb.knowledge_retrieve("int sum(int a, int b) { return a + b; }\n", "C", shots=2)
        assert results
        assert len(results) <= 2
        assert all("qualified_name" in result for result in results)
        assert all("containment" in result for result in results)
        known_names = {"hello", "add", "mul"}
        for result in results:
            assert result["qualified_name"] in known_names, (
                f"检索结果 qualified_name 应在已知函数中，实际 '{result['qualified_name']}'"
            )
        assert results[0]["qualified_name"] == "add", (
            f"查询 a+b 的最相似结果应是 add，实际 '{results[0]['qualified_name']}'"
        )
        print("✓ test_knowledge_retrieval passed")
    finally:
        cleanup()


def test_knowledge_retrieval_many():
    cleanup()
    try:
        kb = KnowledgeBase(TEST_DB_PATH, min_lines=0)
        snippets = [
            ("int hello() { return 1; }\n", "hello.c", "test1"),
            ("int add(int a, int b) { return a + b; }\n", "add.c", "test2"),
            ("int mul(int a, int b) { return a * b; }\n", "mul.c", "test3"),
        ]

        for content, file_path, repo in snippets:
            records = kb.process_file_from_content(content, file_path, repo, file_path)
            kb.update_database_from_records(records)

        results = kb.knowledge_retrieve_many(
            [
                "int sum(int a, int b) { return a + b; }\n",
                "int product(int a, int b) { return a * b; }\n",
            ],
            "C",
            shots=2,
            max_workers=1,
        )
        assert len(results) == 2
        assert all(isinstance(item, list) for item in results)
        assert all(result and "qualified_name" in result[0] for result in results)
        assert all("containment" in result[0] for result in results)
        print("✓ test_knowledge_retrieval_many passed")
    finally:
        cleanup()


def test_information_retrieval():
    cleanup()
    try:
        kb = KnowledgeBase(TEST_DB_PATH, min_lines=0)
        snippets = [
            (
                "/* allocate memory for a new buffer */\nint *alloc_buffer(void) { return 0; }\n",
                "alloc.c",
                "test1",
            ),
            (
                "/* print a greeting message to stdout */\nvoid greet(void) {}\n",
                "print.c",
                "test2",
            ),
        ]

        for content, file_path, repo in snippets:
            records = kb.process_file_from_content(content, file_path, repo, file_path)
            kb.update_database_from_records(records)

        results = kb.information_retrieve("allocate memory for a new buffer", shots=2)
        assert results
        assert results[0]["qualified_name"] == "alloc_buffer", (
            f"查询 'allocate memory' 最相似应是 alloc_buffer，实际 '{results[0]['qualified_name']}'"
        )
        assert "text" in results[0]
        assert "containment" in results[0]
        assert results[0]["containment"] > 0, "最佳匹配的相似度应 > 0"
        assert results[0]["kind"] == "function"
        print("✓ test_information_retrieval passed")
    finally:
        cleanup()


def test_information_retrieval_many():
    cleanup()
    try:
        kb = KnowledgeBase(TEST_DB_PATH, min_lines=0)
        snippets = [
            (
                "/* allocate memory for a new buffer */\nint *alloc_buffer(void) { return 0; }\n",
                "alloc.c",
                "test1",
            ),
            (
                "/* print a greeting message to stdout */\nvoid greet(void) {}\n",
                "print.c",
                "test2",
            ),
        ]

        for content, file_path, repo in snippets:
            records = kb.process_file_from_content(content, file_path, repo, file_path)
            kb.update_database_from_records(records)

        results = kb.information_retrieve_many(
            ["allocate memory for a new buffer", "print a greeting message to stdout"],
            shots=2,
            max_workers=1,
        )
        assert len(results) == 2
        assert results[0]
        assert results[1]
        assert "text" in results[0][0]
        assert "containment" in results[0][0]
        print("✓ test_information_retrieval_many passed")
    finally:
        cleanup()


def main():
    print("测试知识检索集成功能...")
    print("=" * 60)

    try:
        test_fingerprint_generation()
        test_database_storage()
        test_knowledge_retrieval()
        test_knowledge_retrieval_many()
        test_information_retrieval()
        test_information_retrieval_many()

        print("=" * 60)
        print("✓ 所有知识检索集成测试通过！")
        return 0
    except AssertionError as exc:
        print("=" * 60)
        print(f"✗ 测试失败: {exc}")
        return 1
    except Exception as exc:
        print("=" * 60)
        print(f"✗ 意外错误: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
