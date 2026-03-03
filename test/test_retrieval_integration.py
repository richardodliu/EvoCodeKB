#!/usr/bin/env python3
"""
测试知识检索功能
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.knowledgebase import KnowledgeBase
import json


TEST_DB_PATH = 'test_retrieval.db'


def test_fingerprint_generation():
    """测试指纹树生成"""
    # 清理旧数据库
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    try:
        kb = KnowledgeBase(TEST_DB_PATH)

        test_code = """
#include <stdio.h>

int main() {
    int x = 10;
    printf("Hello: %d\\n", x);
    return 0;
}
"""

        record = kb.process_file_from_content(
            content=test_code,
            file_path='test.c',
            repository='test_repo',
            relative_path='test.c'
        )

        assert record.code_fingerprint, "指纹生成失败"

        fp_tree = json.loads(record.code_fingerprint)
        assert len(fp_tree) > 0, "指纹树为空"

        # 验证注释指纹（代码含注释时应生成）
        # 此测试代码无注释，comment_fingerprint 可能为 None
        print(f"  ✓ 指纹树已生成")
        print(f"  ✓ 长度: {len(fp_tree)}")
        print(f"  ✓ 前10个节点: {fp_tree[:10]}")
        print(f"  ✓ comment_fingerprint: {record.comment_fingerprint}")
        print("✓ test_fingerprint_generation passed")
    finally:
        # 清理测试数据库
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)


def test_database_storage():
    """测试数据库存储"""
    # 清理旧数据库
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    try:
        kb = KnowledgeBase(TEST_DB_PATH)

        # 添加多个测试代码
        test_codes = [
            {
                'code': '#include <stdio.h>\nint main() { printf("Hello\\n"); return 0; }',
                'file': 'hello.c',
                'repo': 'test1'
            },
            {
                'code': '#include <stdio.h>\nint main() { int x = 10; printf("%d\\n", x); return 0; }',
                'file': 'print_int.c',
                'repo': 'test2'
            },
            {
                'code': '#include <stdlib.h>\nint main() { int *p = malloc(sizeof(int)); free(p); return 0; }',
                'file': 'malloc.c',
                'repo': 'test3'
            }
        ]

        for item in test_codes:
            record = kb.process_file_from_content(
                content=item['code'],
                file_path=item['file'],
                repository=item['repo'],
                relative_path=item['file']
            )
            kb.update_database_from_dict(record)

        # 验证
        results = kb.database.query(language='C')
        assert len(results) == len(test_codes), f"期望 {len(test_codes)} 条记录，实际 {len(results)} 条"

        print(f"  ✓ 保存了 {len(results)} 条记录")
        for r in results:
            has_fp = "有" if r.code_fingerprint else "无"
            has_cfp = "有" if r.comment_fingerprint else "无"
            print(f"    - {r.relative_path}: 指纹树 {has_fp}, 注释指纹 {has_cfp}")

        print("✓ test_database_storage passed")
    finally:
        # 清理测试数据库
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)


def test_retrieval():
    """测试检索功能"""
    # 清理旧数据库
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    try:
        kb = KnowledgeBase(TEST_DB_PATH)

        # 先添加测试数据
        test_codes = [
            {
                'code': '#include <stdio.h>\nint main() { printf("Hello\\n"); return 0; }',
                'file': 'hello.c',
                'repo': 'test1'
            },
            {
                'code': '#include <stdio.h>\nint main() { int x = 10; printf("%d\\n", x); return 0; }',
                'file': 'print_int.c',
                'repo': 'test2'
            },
            {
                'code': '#include <stdlib.h>\nint main() { int *p = malloc(sizeof(int)); free(p); return 0; }',
                'file': 'malloc.c',
                'repo': 'test3'
            }
        ]

        for item in test_codes:
            record = kb.process_file_from_content(
                content=item['code'],
                file_path=item['file'],
                repository=item['repo'],
                relative_path=item['file']
            )
            kb.update_database_from_dict(record)

        # 测试查询
        query_code = """
#include <stdio.h>

int main() {
    int y = 20;
    printf("Value: %d\\n", y);
    return 0;
}
"""

        results = kb.knowledge_retrieve(query_code, 'C', shots=3)

        assert results, "未找到相似代码"
        assert len(results) > 0, "结果为空"

        print(f"  ✓ 找到 {len(results)} 个相似代码片段:")
        for i, result in enumerate(results, 1):
            print(f"    {i}. [{result['language']}] {result['repository']} / {result['relative_path']}")
            print(f"       覆盖度: {result['score']:.4f}")

        print("✓ test_retrieval passed")
    finally:
        # 清理测试数据库
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)


def test_information_retrieval():
    """测试基于注释指纹的信息检索"""
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    try:
        kb = KnowledgeBase(TEST_DB_PATH)

        # 添加包含注释的测试代码
        test_codes = [
            {
                'code': '/* print hello message to stdout */\n#include <stdio.h>\nint main() { printf("Hello\\n"); return 0; }',
                'file': 'hello.c',
                'repo': 'test1'
            },
            {
                'code': '/* allocate memory and free resources */\n#include <stdlib.h>\nint main() { int *p = malloc(sizeof(int)); free(p); return 0; }',
                'file': 'malloc.c',
                'repo': 'test2'
            },
        ]

        for item in test_codes:
            record = kb.process_file_from_content(
                content=item['code'],
                file_path=item['file'],
                repository=item['repo'],
                relative_path=item['file']
            )
            kb.update_database_from_dict(record)

        # 用自然语言描述检索
        results = kb.information_retrieve("allocate memory and free", shots=2)

        assert isinstance(results, list), "结果应该是列表"
        print(f"  ✓ information_retrieve 返回 {len(results)} 个结果")
        for i, r in enumerate(results, 1):
            print(f"    {i}. [{r['language']}] {r['repository']} / {r['relative_path']}")
            print(f"       覆盖度: {r['score']:.4f}")
        assert 'comment' in results[0] if results else True, "结果应包含 comment 字段"

        print("✓ test_information_retrieval passed")
    finally:
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)


def main():
    """运行所有测试"""
    print("测试知识检索集成功能...")
    print("=" * 60)

    try:
        test_fingerprint_generation()
        test_database_storage()
        test_retrieval()
        test_information_retrieval()

        print("=" * 60)
        print("✓ 所有知识检索集成测试通过！")
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
