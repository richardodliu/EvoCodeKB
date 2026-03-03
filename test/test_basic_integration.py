#!/usr/bin/env python3
"""
测试 KnowledgeBase 的基本集成功能
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.knowledgebase import KnowledgeBase

# 测试数据库路径
TEST_DB_DIR = Path('knowledgebase')
TEST_DB_DIR.mkdir(exist_ok=True)
TEST_DB_PATH = TEST_DB_DIR / 'test_basic.db'

# 内联测试用 C 代码
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
    if (node == NULL) {
        printf("Memory allocation failed\\n");
        return NULL;
    }
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


def test_process_file():
    """测试单文件处理"""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))
        result = kb.process_file_from_content(
            content=SAMPLE_C_CODE,
            file_path='src/list.c',
            repository='test_repo',
            relative_path='src/list.c'
        )

        assert result.repository == 'test_repo', "仓库名不匹配"
        assert result.relative_path == 'src/list.c', "路径不匹配"
        assert result.language == 'C', "语言不匹配"
        assert len(result.text) > 0, "文本为空"
        assert len(result.code) > 0, "代码为空"
        assert len(result.comment) > 0, "注释为空"

        print(f"  ✓ 文件: {result.relative_path}")
        print(f"  ✓ 语言: {result.language}")
        print(f"  ✓ 文本长度: {len(result.text)}")
        print(f"  ✓ 代码长度: {len(result.code)}")
        print(f"  ✓ 注释长度: {len(result.comment)}")
        print("✓ test_process_file passed")
    finally:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()


def test_update_database():
    """测试数据库更新"""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))
        record = kb.process_file_from_content(
            content=SAMPLE_C_CODE,
            file_path='src/list.c',
            repository='test_repo',
            relative_path='src/list.c'
        )
        kb.update_database_from_dict(record)

        stats = kb.get_stats()
        assert stats['total_files'] >= 1, "数据库中没有文件"
        assert 'test_repo' in stats['by_repository'], "未找到仓库"

        print(f"  ✓ 数据库记录数: {stats['total_files']}")
        print("✓ test_update_database passed")
    finally:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()


def test_search_database():
    """测试数据库搜索"""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))

        record = kb.process_file_from_content(
            content=SAMPLE_C_CODE,
            file_path='src/list.c',
            repository='test_repo',
            relative_path='src/list.c'
        )
        kb.update_database_from_dict(record)

        # 搜索代码
        results = kb.search_database('createNode', search_type='code', language='C')
        assert len(results) > 0, "代码搜索无结果"
        print(f"  ✓ 搜索 'createNode' 在代码中: 找到 {len(results)} 条")

        # 搜索注释
        results = kb.search_database('linked list', search_type='comment', repository='test_repo')
        assert len(results) > 0, "注释搜索无结果"
        print(f"  ✓ 搜索 'linked list' 在注释中: 找到 {len(results)} 条")

        # 按仓库过滤
        results = kb.search_database('malloc', repository='test_repo')
        assert len(results) > 0, "仓库过滤无结果"
        print(f"  ✓ 搜索 'malloc' (repo=test_repo): 找到 {len(results)} 条")
        print("✓ test_search_database passed")
    finally:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()


def test_get_stats():
    """测试统计信息获取"""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    try:
        kb = KnowledgeBase(str(TEST_DB_PATH))

        record = kb.process_file_from_content(
            content=SAMPLE_C_CODE,
            file_path='src/list.c',
            repository='test_repo',
            relative_path='src/list.c'
        )
        kb.update_database_from_dict(record)

        stats = kb.get_stats()
        assert 'total_files' in stats, "缺少 total_files"
        assert 'by_language' in stats, "缺少 by_language"
        assert 'by_repository' in stats, "缺少 by_repository"

        print(f"  ✓ 总文件数: {stats['total_files']}")
        print(f"  ✓ 按语言: {stats['by_language']}")
        print(f"  ✓ 按仓库: {stats['by_repository']}")
        print("✓ test_get_stats passed")
    finally:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()


def main():
    """运行所有测试"""
    print("测试 KnowledgeBase 基本集成功能...")
    print("=" * 60)

    try:
        test_process_file()
        test_update_database()
        test_search_database()
        test_get_stats()

        print("=" * 60)
        print("✓ 所有 KnowledgeBase 基本集成测试通过！")
        return 0
    except AssertionError as e:
        print("=" * 60)
        print(f"✗ 测试失败: {e}")
        return 1
    except Exception as e:
        print("=" * 60)
        print(f"✗ 意外错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
