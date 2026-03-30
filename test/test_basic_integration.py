#!/usr/bin/env python3
"""KnowledgeBase 基本集成功能测试"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evokb.knowledgebase import KnowledgeBase


TEST_DB_PATH = Path(tempfile.mktemp(suffix=".db", prefix="test_basic_"))

SAMPLE_C_CODE = """\
#include <stdio.h>
#include <stdlib.h>

/* A simple linked list node */
struct Node {
    int data;
    struct Node *next;
};

/* Create a new node with the given value */
struct Node* createNode(int value) {
    struct Node *node = (struct Node*)malloc(sizeof(struct Node));
    node->data = value;
    node->next = NULL;
    return node;
}

int main() {
    struct Node *head = createNode(42);
    printf("Node value: %d\\n", head->data);
    free(head);
    return 0;
}
"""


def cleanup():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


def test_process_file():
    cleanup()
    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))
        records = kb.process_file_from_content(
            content=SAMPLE_C_CODE,
            file_path="src/list.c",
            repository="test_repo",
            relative_path="src/list.c",
        )

        assert len(records) >= 3
        qualified_names = {record.qualified_name for record in records}
        assert "Node" in qualified_names
        assert "createNode" in qualified_names
        assert "main" in qualified_names

        create_node = next(record for record in records if record.qualified_name == "createNode")
        assert create_node.start_line < create_node.end_line
        assert "malloc" in create_node.text
        print("✓ test_process_file passed")
    finally:
        cleanup()


def test_update_database():
    cleanup()
    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))
        records = kb.process_file_from_content(
            content=SAMPLE_C_CODE,
            file_path="src/list.c",
            repository="test_repo",
            relative_path="src/list.c",
        )
        kb.update_database_from_records(records)

        stats = kb.get_stats()
        assert stats["total_entries"] == len(records)
        assert "test_repo" in stats["by_repository"]
        print("✓ test_update_database passed")
    finally:
        cleanup()


def test_search_database():
    cleanup()
    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))
        records = kb.process_file_from_content(
            content=SAMPLE_C_CODE,
            file_path="src/list.c",
            repository="test_repo",
            relative_path="src/list.c",
        )
        kb.update_database_from_records(records)

        results = kb.search_database("createNode", language="C", kind="function")
        assert len(results) > 0

        results = kb.search_database("linked list", repository="test_repo", kind="type")
        assert len(results) > 0

        results = kb.search_database("malloc", repository="test_repo")
        assert len(results) > 0
        print("✓ test_search_database passed")
    finally:
        cleanup()


def test_get_stats():
    cleanup()
    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))
        records = kb.process_file_from_content(
            content=SAMPLE_C_CODE,
            file_path="src/list.c",
            repository="test_repo",
            relative_path="src/list.c",
        )
        kb.update_database_from_records(records)

        stats = kb.get_stats()
        assert "total_entries" in stats
        assert "by_language" in stats
        assert "by_repository" in stats
        assert "by_kind" in stats
        print("✓ test_get_stats passed")
    finally:
        cleanup()


def test_invalid_code_still_imported():
    cleanup()
    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))
        invalid_c_code = """\
#include <stdio.h>

int broken( {
    printf("oops");
"""

        records = kb.process_file_from_content(
            content=invalid_c_code,
            file_path="src/broken.c",
            repository="test_repo",
            relative_path="src/broken.c",
        )
        kb.update_database_from_records(records)

        stats = kb.get_stats()
        assert stats["total_entries"] > 0, "坏代码也应该生成至少一个条目"
        stored = kb.database.query(repository="test_repo")
        assert any("oops" in record.text for record in stored), "源码文本应该被保留入库"
        print("✓ test_invalid_code_still_imported passed")
    finally:
        cleanup()


def test_header_files_use_cpp_parsing():
    cleanup()
    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))
        header_code = """\
class Widget {
public:
    void setValue(int value) {
        value_ = value;
    }

private:
    int value_{0};
};
"""

        records = kb.process_file_from_content(
            content=header_code,
            file_path="include/widget.h",
            repository="test_repo",
            relative_path="include/widget.h",
        )

        assert records, ".h 文件应该生成语义条目"
        assert all(record.language == "C" for record in records), ".h 文件应按 C++ 解析"

        qualified_names = {record.qualified_name for record in records}
        assert "Widget" in qualified_names, "类定义应该被识别"
        assert "Widget::setValue" in qualified_names, "类方法应该被识别"
        assert all(
            record.symbol_name != "value_" for record in records if record.kind in {"function", "method"}
        ), "成员变量不应被误识别成函数/方法"
        print("✓ test_header_files_use_cpp_parsing passed")
    finally:
        cleanup()


def main():
    print("测试 KnowledgeBase 基本集成功能...")
    print("=" * 60)

    try:
        test_process_file()
        test_update_database()
        test_search_database()
        test_get_stats()
        test_invalid_code_still_imported()
        test_header_files_use_cpp_parsing()

        print("=" * 60)
        print("✓ 所有 KnowledgeBase 基本集成测试通过！")
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
