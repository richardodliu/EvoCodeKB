#!/usr/bin/env python3
"""Database 单元测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.storage.database import Database
from evokb.storage.models import CodeRecord


def setup_test_db():
    """创建临时测试数据库"""
    return tempfile.mktemp(suffix='.db')


def cleanup_test_db(db_path):
    """清理测试数据库"""
    if os.path.exists(db_path):
        os.remove(db_path)


def test_database_initialization():
    """测试数据库初始化"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        assert os.path.exists(db_path), "数据库文件应该被创建"

        # 验证表是否创建
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='code_knowledge'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None, "code_knowledge 表应该被创建"

        print("✓ test_database_initialization passed")
    finally:
        cleanup_test_db(db_path)


def test_insert_record():
    """测试插入记录"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)

        record = CodeRecord(
            repository="test_repo",
            relative_path="test.c",
            text="int main() { return 0; }",
            code="int main() { return 0; }",
            comment="Test comment",
            file_extension=".c",
            language="C",
            code_fingerprint="[1, 2, 3]",
            comment_fingerprint="[4, 5, 6]"
        )

        db.insert(record)

        # 验证插入
        results = db.query()
        assert len(results) == 1, f"应该有 1 条记录，实际有 {len(results)} 条"
        assert results[0].repository == "test_repo", "仓库名应该匹配"
        assert results[0].language == "C", "语言应该匹配"
        assert results[0].comment_fingerprint == "[4, 5, 6]", "注释指纹应该匹配"

        print("✓ test_insert_record passed")
    finally:
        cleanup_test_db(db_path)


def test_insert_duplicate():
    """测试插入重复记录"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)

        record = CodeRecord(
            repository="test_repo",
            relative_path="test.c",
            text="int main() { return 0; }",
            code="int main() { return 0; }",
            comment="",
            file_extension=".c",
            language="C"
        )

        # 第一次插入
        db.insert(record)

        # 第二次插入相同记录（应该被忽略或更新）
        db.insert(record)

        results = db.query()
        # 由于有唯一约束，应该只有一条记录
        assert len(results) == 1, "重复插入应该被处理"

        print("✓ test_insert_duplicate passed")
    finally:
        cleanup_test_db(db_path)


def test_query_by_language():
    """测试按语言查询"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)

        # 插入不同语言的记录
        record_c = CodeRecord(
            repository="test_repo",
            relative_path="test.c",
            text="int main() {}",
            code="int main() {}",
            comment="",
            file_extension=".c",
            language="C"
        )
        record_py = CodeRecord(
            repository="test_repo",
            relative_path="test.py",
            text="def main(): pass",
            code="def main(): pass",
            comment="",
            file_extension=".py",
            language="Python"
        )

        db.insert(record_c)
        db.insert(record_py)

        # 查询 C 语言
        results = db.query(language="C")
        assert len(results) == 1, f"应该有 1 条 C 记录，实际有 {len(results)} 条"
        assert results[0].language == "C", "查询结果应该是 C 语言"

        # 查询 Python
        results = db.query(language="Python")
        assert len(results) == 1, f"应该有 1 条 Python 记录，实际有 {len(results)} 条"
        assert results[0].language == "Python", "查询结果应该是 Python"

        print("✓ test_query_by_language passed")
    finally:
        cleanup_test_db(db_path)


def test_query_by_repository():
    """测试按仓库查询"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)

        # 插入不同仓库的记录
        record1 = CodeRecord(
            repository="repo1",
            relative_path="test.c",
            text="code1",
            code="code1",
            comment="",
            file_extension=".c",
            language="C"
        )
        record2 = CodeRecord(
            repository="repo2",
            relative_path="test.c",
            text="code2",
            code="code2",
            comment="",
            file_extension=".c",
            language="C"
        )

        db.insert(record1)
        db.insert(record2)

        # 查询 repo1
        results = db.query(repository="repo1")
        assert len(results) == 1, f"应该有 1 条 repo1 记录，实际有 {len(results)} 条"
        assert results[0].repository == "repo1", "查询结果应该是 repo1"

        print("✓ test_query_by_repository passed")
    finally:
        cleanup_test_db(db_path)


def test_get_stats():
    """测试统计信息"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)

        # 插入测试数据
        for i in range(5):
            record = CodeRecord(
                repository="test_repo",
                relative_path=f"test{i}.c",
                text=f"code{i}",
                code=f"code{i}",
                comment="",
                file_extension=".c",
                language="C"
            )
            db.insert(record)

        stats = db.get_stats()
        assert stats['total_files'] == 5, f"应该有 5 条记录，实际有 {stats['total_files']} 条"
        assert 'C' in stats['by_language'], "统计中应该包含 C 语言"
        assert stats['by_language']['C'] == 5, f"C 语言应该有 5 条记录"

        print("✓ test_get_stats passed")
    finally:
        cleanup_test_db(db_path)


def test_query_all():
    """测试查询所有记录"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)

        # 插入多条记录
        for i in range(3):
            record = CodeRecord(
                repository="test_repo",
                relative_path=f"test{i}.c",
                text=f"code{i}",
                code=f"code{i}",
                comment="",
                file_extension=".c",
                language="C"
            )
            db.insert(record)

        results = db.query()
        assert len(results) == 3, f"应该有 3 条记录，实际有 {len(results)} 条"

        print("✓ test_query_all passed")
    finally:
        cleanup_test_db(db_path)


def main():
    print("Testing Database...")
    print("=" * 60)

    try:
        test_database_initialization()
        test_insert_record()
        test_insert_duplicate()
        test_query_by_language()
        test_query_by_repository()
        test_get_stats()
        test_query_all()

        print("=" * 60)
        print("✓ All Database tests passed!")
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
