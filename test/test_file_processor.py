#!/usr/bin/env python3
"""FileProcessor 单元测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.io.file_processor import FileProcessor
from evokb.config.manager import ConfigManager


def setup_test_dir():
    """创建临时测试目录"""
    temp_dir = tempfile.mkdtemp()
    return temp_dir


def cleanup_test_dir(temp_dir):
    """清理测试目录"""
    import shutil
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


def test_read_file():
    """测试读取文件"""
    temp_dir = setup_test_dir()
    try:
        config_mgr = ConfigManager()
        processor = FileProcessor(config_mgr)

        # 创建测试文件
        test_file = os.path.join(temp_dir, "test.c")
        content = "int main() { return 0; }"
        with open(test_file, 'w') as f:
            f.write(content)

        # 读取文件
        result = processor.read_file(test_file)
        assert result == content, f"读取的内容应该匹配，期望 '{content}'，实际 '{result}'"

        print("✓ test_read_file passed")
    finally:
        cleanup_test_dir(temp_dir)


def test_read_nonexistent_file():
    """测试读取不存在的文件"""
    config_mgr = ConfigManager()
    processor = FileProcessor(config_mgr)

    try:
        result = processor.read_file("/nonexistent/path/file.c")
        assert False, "应该抛出异常"
    except (FileNotFoundError, IOError):
        # 预期会抛出异常
        pass

    print("✓ test_read_nonexistent_file passed")


def test_get_files_by_extension():
    """测试按扩展名获取文件"""
    temp_dir = setup_test_dir()
    try:
        config_mgr = ConfigManager()
        processor = FileProcessor(config_mgr)

        # 创建多个文件
        files = ["test1.c", "test2.c", "test.py", "test.txt"]
        for filename in files:
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, 'w') as f:
                f.write("content")

        # 获取 .c 文件
        c_files = processor.get_files_by_extension(temp_dir, [".c"])
        assert len(c_files) == 2, f"应该找到 2 个 .c 文件，实际找到 {len(c_files)} 个"

        # 获取 .py 文件
        py_files = processor.get_files_by_extension(temp_dir, [".py"])
        assert len(py_files) == 1, f"应该找到 1 个 .py 文件，实际找到 {len(py_files)} 个"

        print("✓ test_get_files_by_extension passed")
    finally:
        cleanup_test_dir(temp_dir)


def test_recursive_directory_traversal():
    """测试递归目录遍历"""
    temp_dir = setup_test_dir()
    try:
        config_mgr = ConfigManager()
        processor = FileProcessor(config_mgr)

        # 创建嵌套目录结构
        subdir = os.path.join(temp_dir, "subdir")
        os.makedirs(subdir)

        # 在不同层级创建文件
        with open(os.path.join(temp_dir, "test1.c"), 'w') as f:
            f.write("content")
        with open(os.path.join(subdir, "test2.c"), 'w') as f:
            f.write("content")

        # 递归获取所有 .c 文件（rglob 默认递归）
        c_files = processor.get_files_by_extension(temp_dir, [".c"])
        assert len(c_files) >= 2, f"应该找到至少 2 个 .c 文件（递归），实际找到 {len(c_files)} 个"

        print("✓ test_recursive_directory_traversal passed")
    finally:
        cleanup_test_dir(temp_dir)


def test_empty_directory():
    """测试空目录"""
    temp_dir = setup_test_dir()
    try:
        config_mgr = ConfigManager()
        processor = FileProcessor(config_mgr)

        # 获取空目录中的文件
        files = processor.get_files_by_extension(temp_dir, [".c"])
        assert len(files) == 0, "空目录应该返回空列表"

        print("✓ test_empty_directory passed")
    finally:
        cleanup_test_dir(temp_dir)


def test_read_file_with_encoding():
    """测试读取不同编码的文件"""
    temp_dir = setup_test_dir()
    try:
        config_mgr = ConfigManager()
        processor = FileProcessor(config_mgr)

        # 创建 UTF-8 文件
        test_file = os.path.join(temp_dir, "test.c")
        content = "// 中文注释\nint main() { return 0; }"
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # 读取文件
        result = processor.read_file(test_file)
        assert result is not None, "应该能读取 UTF-8 文件"
        assert "中文" in result, "应该能正确读取中文内容"

        print("✓ test_read_file_with_encoding passed")
    finally:
        cleanup_test_dir(temp_dir)


def main():
    print("Testing FileProcessor...")
    print("=" * 60)

    try:
        test_read_file()
        test_read_nonexistent_file()
        test_get_files_by_extension()
        test_recursive_directory_traversal()
        test_empty_directory()
        test_read_file_with_encoding()

        print("=" * 60)
        print("✓ All FileProcessor tests passed!")
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
