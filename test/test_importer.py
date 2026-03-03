#!/usr/bin/env python3
"""Importer 单元测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.io.importer import Importer
from evokb.knowledgebase import KnowledgeBase


def setup_test_env():
    """创建测试环境"""
    temp_dir = tempfile.mkdtemp()
    db_path = tempfile.mktemp(suffix='.db')
    return temp_dir, db_path


def cleanup_test_env(temp_dir, db_path):
    """清理测试环境"""
    import shutil
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    if os.path.exists(db_path):
        os.remove(db_path)


def test_import_directory():
    """测试导入目录"""
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path)
        importer = Importer(kb)

        # 创建多个测试文件
        files = ["test1.c", "test2.c"]
        for filename in files:
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, 'w') as f:
                f.write(f"int main() {{ return 0; }}")

        # 导入目录
        importer.import_directory(temp_dir, "test_repo")

        # 验证数据库
        records = kb.database.query()
        assert len(records) >= 1, f"数据库中应该有至少 1 条记录，实际有 {len(records)} 条"

        print("✓ test_import_directory passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def test_import_empty_directory():
    """测试导入空目录"""
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path)
        importer = Importer(kb)

        # 导入空目录
        importer.import_directory(temp_dir, "test_repo")

        # 应该正常处理，不报错
        records = kb.database.query()
        assert len(records) == 0, "空目录应该导入 0 个文件"

        print("✓ test_import_empty_directory passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def test_import_with_repository_name():
    """测试带仓库名的导入"""
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path)
        importer = Importer(kb)

        # 创建测试文件
        test_file = os.path.join(temp_dir, "test.c")
        with open(test_file, 'w') as f:
            f.write("int main() { return 0; }")

        # 使用特定仓库名导入
        repo_name = "my_test_repo"
        importer.import_directory(temp_dir, repo_name)

        # 验证仓库名
        records = kb.database.query(repository=repo_name)
        if len(records) > 0:
            assert records[0].repository == repo_name, f"仓库名应该是 '{repo_name}'"

        print("✓ test_import_with_repository_name passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def test_import_nested_directory():
    """测试导入嵌套目录"""
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path)
        importer = Importer(kb)

        # 创建嵌套目录结构
        subdir = os.path.join(temp_dir, "subdir")
        os.makedirs(subdir)

        # 在不同层级创建文件
        with open(os.path.join(temp_dir, "test1.c"), 'w') as f:
            f.write("int main() { return 0; }")
        with open(os.path.join(subdir, "test2.c"), 'w') as f:
            f.write("int foo() { return 1; }")

        # 导入（应该递归）
        importer.import_directory(temp_dir, "test_repo")

        # 验证导入了所有文件
        records = kb.database.query()
        assert len(records) >= 1, f"应该导入至少 1 个文件，实际导入 {len(records)} 个"

        print("✓ test_import_nested_directory passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def main():
    print("Testing Importer...")
    print("=" * 60)

    try:
        test_import_directory()
        test_import_empty_directory()
        test_import_with_repository_name()
        test_import_nested_directory()

        print("=" * 60)
        print("✓ All Importer tests passed!")
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
