#!/usr/bin/env python3
"""InformationRetrieval 单元测试"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.retrieval.information_retrieval import InformationRetrieval
from evokb.fingerprint.comment_generator import CommentFingerprintGenerator
from evokb.storage.database import Database
from evokb.storage.models import CodeRecord


def setup_test_db():
    """创建临时测试数据库"""
    return tempfile.mktemp(suffix='.db')


def cleanup_test_db(db_path):
    """清理测试数据库"""
    if os.path.exists(db_path):
        os.remove(db_path)


def insert_test_records(db, comment_fp_gen):
    """插入带注释指纹的测试记录"""
    records = [
        CodeRecord(
            repository="repo1",
            relative_path="alloc.c",
            text="int *p = malloc(sizeof(int));",
            code="int *p = malloc(sizeof(int));",
            comment="allocate dynamic memory for the integer pointer buffer",
            file_extension=".c",
            language="C",
            comment_fingerprint=json.dumps(
                comment_fp_gen.generate("allocate dynamic memory for the integer pointer buffer")
            ),
        ),
        CodeRecord(
            repository="repo2",
            relative_path="free.c",
            text="free(p);",
            code="free(p);",
            comment="free all previously allocated resources after program use",
            file_extension=".c",
            language="C",
            comment_fingerprint=json.dumps(
                comment_fp_gen.generate("free all previously allocated resources after program use")
            ),
        ),
        CodeRecord(
            repository="repo3",
            relative_path="print.c",
            text='printf("hello");',
            code='printf("hello");',
            comment="print the output string message to the standard console",
            file_extension=".c",
            language="C",
            comment_fingerprint=json.dumps(
                comment_fp_gen.generate("print the output string message to the standard console")
            ),
        ),
    ]
    for r in records:
        db.insert(r)
    return records


def test_empty_database():
    """测试空数据库返回空列表"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        gen = CommentFingerprintGenerator()
        ir = InformationRetrieval(db, gen)
        results = ir.retrieve("allocate memory", shots=3)
        assert results == [], f"空数据库应返回空列表，实际 {results}"
        print("✓ test_empty_database passed")
    finally:
        cleanup_test_db(db_path)


def test_empty_input():
    """测试空输入返回空列表"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        gen = CommentFingerprintGenerator()
        ir = InformationRetrieval(db, gen)
        assert ir.retrieve("", shots=3) == [], "空字符串应返回空列表"
        assert ir.retrieve("***", shots=3) == [], "纯符号应返回空列表"
        print("✓ test_empty_input passed")
    finally:
        cleanup_test_db(db_path)


def test_normal_retrieval():
    """测试正常检索流程"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        gen = CommentFingerprintGenerator()
        ir = InformationRetrieval(db, gen)
        insert_test_records(db, gen)

        results = ir.retrieve("allocate dynamic memory for the integer pointer", shots=3)
        assert len(results) > 0, "应找到结果"
        assert results[0]['score'] > 0, "最佳匹配覆盖度应 > 0"
        # 最佳匹配应是 alloc.c（注释最相关）
        assert results[0]['relative_path'] == "alloc.c", \
            f"最佳匹配应是 alloc.c，实际 {results[0]['relative_path']}"
        # 输出应包含 comment 字段
        assert 'comment' in results[0], "输出应包含 comment 字段"
        print("✓ test_normal_retrieval passed")
    finally:
        cleanup_test_db(db_path)


def test_shots_limit():
    """测试 shots 限制"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        gen = CommentFingerprintGenerator()
        ir = InformationRetrieval(db, gen)
        insert_test_records(db, gen)

        results = ir.retrieve("allocate dynamic memory for the integer pointer", shots=1)
        assert len(results) == 1, f"shots=1 应只返回 1 个结果，实际 {len(results)}"

        results = ir.retrieve("allocate dynamic memory for the integer pointer", shots=2)
        assert len(results) == 2, f"shots=2 应返回 2 个结果，实际 {len(results)}"
        print("✓ test_shots_limit passed")
    finally:
        cleanup_test_db(db_path)


def test_get_coverage():
    """测试覆盖度计算"""
    db = None  # 不需要数据库
    gen = CommentFingerprintGenerator()
    ir = InformationRetrieval.__new__(InformationRetrieval)

    # 完全覆盖
    assert ir._get_coverage([1, 2, 3], [1, 2, 3]) == 1.0, "完全覆盖应为 1.0"

    # 部分覆盖
    coverage = ir._get_coverage([1, 2], [1, 2, 3])
    assert abs(coverage - 2.0/3.0) < 1e-9, f"部分覆盖应为 2/3，实际 {coverage}"

    # 无覆盖
    assert ir._get_coverage([4, 5], [1, 2, 3]) == 0.0, "无交集应为 0"

    # 空参考树
    assert ir._get_coverage([1, 2], []) == 0.0, "空参考树应为 0"

    print("✓ test_get_coverage passed")


def test_update_tree():
    """测试树更新"""
    ir = InformationRetrieval.__new__(InformationRetrieval)

    result = ir._update_tree([1, 2], [1, 2, 3, 4])
    assert set(result) == {3, 4}, f"应移除已覆盖节点，实际 {result}"

    result = ir._update_tree([5], [1, 2, 3])
    assert set(result) == {1, 2, 3}, "无交集时不应移除任何节点"

    print("✓ test_update_tree passed")


def test_language_filter():
    """测试语言过滤"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        gen = CommentFingerprintGenerator()
        ir = InformationRetrieval(db, gen)

        # 插入 C 和 Python 记录
        db.insert(CodeRecord(
            repository="repo1", relative_path="test.c",
            text="code", code="code",
            comment="allocate dynamic memory buffer for data",
            file_extension=".c", language="C",
            comment_fingerprint=json.dumps(
                gen.generate("allocate dynamic memory buffer for data")
            ),
        ))
        db.insert(CodeRecord(
            repository="repo2", relative_path="test.py",
            text="code", code="code",
            comment="allocate dynamic memory buffer for data",
            file_extension=".py", language="Python",
            comment_fingerprint=json.dumps(
                gen.generate("allocate dynamic memory buffer for data")
            ),
        ))

        results_c = ir.retrieve("allocate dynamic memory buffer for data", language="C", shots=5)
        assert all(r['language'] == 'C' for r in results_c), "语言过滤应只返回 C"

        results_py = ir.retrieve("allocate dynamic memory buffer for data", language="Python", shots=5)
        assert all(r['language'] == 'Python' for r in results_py), "语言过滤应只返回 Python"

        print("✓ test_language_filter passed")
    finally:
        cleanup_test_db(db_path)


def main():
    print("Testing InformationRetrieval...")
    print("=" * 60)

    try:
        test_empty_database()
        test_empty_input()
        test_normal_retrieval()
        test_shots_limit()
        test_get_coverage()
        test_update_tree()
        test_language_filter()

        print("=" * 60)
        print("✓ All InformationRetrieval tests passed!")
        return 0
    except AssertionError as e:
        print("=" * 60)
        print(f"✗ Test failed: {e}")
        return 1
    except Exception as e:
        print("=" * 60)
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
