#!/usr/bin/env python3
"""KnowledgeRetrieval 单元测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.retrieval.knowledge_retrieval import KnowledgeRetrieval
from evokb.fingerprint.tree_generator import FingerprintTreeGenerator
from evokb.storage.database import Database
from evokb.storage.models import CodeRecord


def setup_test_db():
    """创建临时测试数据库"""
    return tempfile.mktemp(suffix='.db')


def cleanup_test_db(db_path):
    """清理测试数据库"""
    if os.path.exists(db_path):
        os.remove(db_path)


def test_get_coverage_calculation():
    """测试覆盖度计算"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        retrieval = KnowledgeRetrieval(db, FingerprintTreeGenerator())

        # 测试完全覆盖
        cand_tree = [1, 2, 3, 4, 5]
        refer_tree = [1, 2, 3]
        coverage = retrieval._get_coverage(cand_tree, refer_tree)
        assert coverage == 1.0, f"完全覆盖应该是 1.0，实际是 {coverage}"

        # 测试部分覆盖
        cand_tree = [1, 2]
        refer_tree = [1, 2, 3, 4]
        coverage = retrieval._get_coverage(cand_tree, refer_tree)
        assert coverage == 0.5, f"50% 覆盖应该是 0.5，实际是 {coverage}"

        # 测试无覆盖
        cand_tree = [5, 6, 7]
        refer_tree = [1, 2, 3]
        coverage = retrieval._get_coverage(cand_tree, refer_tree)
        assert coverage == 0.0, f"无覆盖应该是 0.0，实际是 {coverage}"

        # 测试空参考树
        cand_tree = [1, 2, 3]
        refer_tree = []
        coverage = retrieval._get_coverage(cand_tree, refer_tree)
        assert coverage == 0.0, f"空参考树应该返回 0.0，实际是 {coverage}"

        print("✓ test_get_coverage_calculation passed")
    finally:
        cleanup_test_db(db_path)


def test_update_tree_logic():
    """测试树更新逻辑"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        retrieval = KnowledgeRetrieval(db, FingerprintTreeGenerator())

        # 测试移除已覆盖节点
        cand_tree = [1, 2, 3]
        refer_tree = [1, 2, 3, 4, 5]
        updated_tree = retrieval._update_tree(cand_tree, refer_tree)

        assert 1 not in updated_tree, "节点 1 应该被移除"
        assert 2 not in updated_tree, "节点 2 应该被移除"
        assert 3 not in updated_tree, "节点 3 应该被移除"
        assert 4 in updated_tree, "节点 4 应该保留"
        assert 5 in updated_tree, "节点 5 应该保留"
        assert len(updated_tree) == 2, f"更新后应该剩余 2 个节点，实际是 {len(updated_tree)}"

        # 测试无交集
        cand_tree = [6, 7, 8]
        refer_tree = [1, 2, 3]
        updated_tree = retrieval._update_tree(cand_tree, refer_tree)
        assert updated_tree == [1, 2, 3], "无交集时参考树应保持不变"

        print("✓ test_update_tree_logic passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_empty_database():
    """测试空数据库检索"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        retrieval = KnowledgeRetrieval(db, FingerprintTreeGenerator())

        input_code = "int main() { return 0; }"
        results = retrieval.retrieve(input_code, "C", shots=5)

        assert results == [], "空数据库应返回空列表"
        print("✓ test_retrieve_empty_database passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_normal_flow():
    """测试正常检索流程"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        import json
        code1 = "int main() { return 0; }"
        code2 = "int foo(int x) { return x + 1; }"

        fp1 = fp_gen.generate_fp_tree(code1, "C")
        fp2 = fp_gen.generate_fp_tree(code2, "C")
        assert fp1 is not None, "应该能生成 code1 的指纹"
        assert fp2 is not None, "应该能生成 code2 的指纹"

        record1 = CodeRecord(
            repository="test_repo",
            relative_path="test1.c",
            text=code1,
            code=code1,
            comment="// main entry",
            file_extension=".c",
            language="C",
            code_fingerprint=json.dumps(fp1)
        )
        record2 = CodeRecord(
            repository="test_repo",
            relative_path="test2.c",
            text=code2,
            code=code2,
            comment="// foo function",
            file_extension=".c",
            language="C",
            code_fingerprint=json.dumps(fp2)
        )

        db.insert(record1)
        db.insert(record2)

        # 用 code1 作为输入检索，code1 本身应该是最佳匹配
        results = retrieval.retrieve(code1, "C", shots=2)

        assert len(results) > 0, "应至少返回一个结果"
        assert len(results) <= 2, "应最多返回 2 个结果"
        assert results[0]['code'] == code1, "最佳匹配应是 code1 本身"
        assert results[0]['score'] > 0, "得分应为正数"
        assert 'comment' in results[0], "结果应包含 comment 字段"

        print("✓ test_retrieve_normal_flow passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_with_shots_limit():
    """测试 shots 参数限制"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        import json
        codes = [
            "int f0() { return 0; }",
            "int f1(int x) { return x; }",
            "int f2(int a, int b) { return a + b; }",
            "void f3() { int x = 0; }",
            "int f4() { int y = 1; return y; }",
        ]

        for i, code in enumerate(codes):
            fp = fp_gen.generate_fp_tree(code, "C")
            assert fp is not None, f"应该能生成 code{i} 的指纹"
            record = CodeRecord(
                repository="test_repo",
                relative_path=f"test{i}.c",
                text=code,
                code=code,
                comment="",
                file_extension=".c",
                language="C",
                code_fingerprint=json.dumps(fp)
            )
            db.insert(record)

        input_code = "int main() { return 0; }"

        # 测试 shots=3
        results_3 = retrieval.retrieve(input_code, "C", shots=3)
        assert len(results_3) <= 3, f"shots=3 应最多返回 3 个结果，实际 {len(results_3)}"
        assert len(results_3) > 0, "应至少返回一个结果"

        # 测试 shots=1
        results_1 = retrieval.retrieve(input_code, "C", shots=1)
        assert len(results_1) == 1, f"shots=1 应返回 1 个结果，实际 {len(results_1)}"

        print("✓ test_retrieve_with_shots_limit passed")
    finally:
        cleanup_test_db(db_path)


def main():
    print("Testing KnowledgeRetrieval...")
    print("=" * 60)

    try:
        test_get_coverage_calculation()
        test_update_tree_logic()
        test_retrieve_empty_database()
        test_retrieve_normal_flow()
        test_retrieve_with_shots_limit()

        print("=" * 60)
        print("✓ All KnowledgeRetrieval tests passed!")
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
