#!/usr/bin/env python3
"""SearchEngine 单元测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.search.engine import SearchEngine
from evokb.storage.database import Database
from evokb.storage.models import CodeRecord


def setup_test_db():
    """创建临时测试数据库"""
    return tempfile.mktemp(suffix='.db')


def cleanup_test_db(db_path):
    """清理测试数据库"""
    if os.path.exists(db_path):
        os.remove(db_path)


def test_search_keyword():
    """测试关键词搜索"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        # 插入测试数据
        record1 = CodeRecord(
            repository="test_repo",
            relative_path="test1.c",
            text="int main() { printf(\"Hello World\"); }",
            code="int main() { printf(\"Hello World\"); }",
            comment="",
            file_extension=".c",
            language="C"
        )
        record2 = CodeRecord(
            repository="test_repo",
            relative_path="test2.c",
            text="int foo() { return 42; }",
            code="int foo() { return 42; }",
            comment="",
            file_extension=".c",
            language="C"
        )

        db.insert(record1)
        db.insert(record2)

        # 搜索 "main"
        results = search_engine.search("main")
        assert len(results) == 1, f"应该找到 1 条包含 'main' 的记录，实际找到 {len(results)} 条"
        assert "main" in results[0]['text'], "结果应该包含 'main'"

        # 搜索 "foo"
        results = search_engine.search("foo")
        assert len(results) == 1, f"应该找到 1 条包含 'foo' 的记录"

        print("✓ test_search_keyword passed")
    finally:
        cleanup_test_db(db_path)


def test_search_empty_query():
    """测试空查询"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        results = search_engine.search("")
        # 空查询应该返回所有记录或空列表
        assert isinstance(results, list), "结果应该是列表"

        print("✓ test_search_empty_query passed")
    finally:
        cleanup_test_db(db_path)


def test_search_with_repository_filter():
    """测试仓库过滤"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        # 插入不同仓库的数据
        record1 = CodeRecord(
            repository="repo1",
            relative_path="test.c",
            text="int main() {}",
            code="int main() {}",
            comment="",
            file_extension=".c",
            language="C"
        )
        record2 = CodeRecord(
            repository="repo2",
            relative_path="test.c",
            text="int main() {}",
            code="int main() {}",
            comment="",
            file_extension=".c",
            language="C"
        )

        db.insert(record1)
        db.insert(record2)

        # 搜索 repo1
        results = search_engine.search("main", repository="repo1")
        assert len(results) == 1, f"应该找到 1 条 repo1 的记录"
        assert results[0]['repository'] == "repo1", "结果应该来自 repo1"

        print("✓ test_search_with_repository_filter passed")
    finally:
        cleanup_test_db(db_path)


def test_search_with_language_filter():
    """测试语言过滤"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        # 插入不同语言的数据
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

        # 搜索 C 语言
        results = search_engine.search("main", language="C")
        assert len(results) == 1, f"应该找到 1 条 C 语言记录"
        assert results[0]['language'] == "C", "结果应该是 C 语言"

        print("✓ test_search_with_language_filter passed")
    finally:
        cleanup_test_db(db_path)


def test_search_no_results():
    """测试无结果搜索"""
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        search_engine = SearchEngine(db)

        # 插入测试数据
        record = CodeRecord(
            repository="test_repo",
            relative_path="test.c",
            text="int main() {}",
            code="int main() {}",
            comment="",
            file_extension=".c",
            language="C"
        )
        db.insert(record)

        # 搜索不存在的关键词
        results = search_engine.search("nonexistent_keyword_xyz")
        assert len(results) == 0, "应该返回空结果"

        print("✓ test_search_no_results passed")
    finally:
        cleanup_test_db(db_path)


def main():
    print("Testing SearchEngine...")
    print("=" * 60)

    try:
        test_search_keyword()
        test_search_empty_query()
        test_search_with_repository_filter()
        test_search_with_language_filter()
        test_search_no_results()

        print("=" * 60)
        print("✓ All SearchEngine tests passed!")
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
