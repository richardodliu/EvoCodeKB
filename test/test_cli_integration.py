#!/usr/bin/env python3
"""
测试 main.py 命令行接口
"""

import subprocess
import sys
import os
import tempfile
import zipfile
import shutil
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 测试用知识库名称
TEST_KB_NAME = 'test_cli'
TEST_DB_PATH = Path('knowledgebase') / f'{TEST_KB_NAME}.db'

# 项目根目录（main.py 所在目录）
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..')

# 内联测试用 C 代码
SAMPLE_C_FILES = {
    'test_repo/src/hello.c': """\
#include <stdio.h>

/* Print a greeting message */
int main() {
    printf("Hello, World!\\n");
    return 0;
}
""",
    'test_repo/src/util.c': """\
#include <stdlib.h>
#include <string.h>

/* Duplicate a string using malloc */
char* my_strdup(const char *s) {
    size_t len = strlen(s) + 1;
    char *dup = (char*)malloc(len);
    if (dup) {
        memcpy(dup, s, len);
    }
    return dup;
}
""",
}


def run_command(cmd):
    """运行命令并返回输出"""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=PROJECT_ROOT
    )
    return result.returncode, result.stdout, result.stderr


def create_test_zip(tmp_dir):
    """创建包含测试 C 文件的 zip 压缩包"""
    zip_path = os.path.join(tmp_dir, 'test_repo.zip')
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for file_path, content in SAMPLE_C_FILES.items():
            zf.writestr(file_path, content)
    return tmp_dir


def cleanup():
    """清理测试数据库"""
    db_path = os.path.join(PROJECT_ROOT, str(TEST_DB_PATH))
    if os.path.exists(db_path):
        os.remove(db_path)


def test_reset_database():
    """测试数据库重置（直接清理并重建）"""
    cleanup()
    # 创建空知识库
    code, out, err = run_command(f"python main.py stats --knowledge_base {TEST_KB_NAME}")
    assert code == 0, f"创建空数据库失败: {err}"
    print("✓ test_reset_database passed")


def test_stats_empty():
    """测试空数据库统计"""
    code, out, err = run_command(f"python main.py stats --knowledge_base {TEST_KB_NAME}")
    assert code == 0, f"统计命令失败: {err}"
    assert "总文件数: 0" in out, f"空数据库统计信息不正确, 输出: {out}"
    print("✓ test_stats_empty passed")


def test_import_repository():
    """测试仓库导入"""
    tmp_dir = tempfile.mkdtemp()
    try:
        data_dir = create_test_zip(tmp_dir)
        code, out, err = run_command(
            f"python main.py update --knowledge_path {data_dir} "
            f"--knowledge_base {TEST_KB_NAME}"
        )
        assert code == 0, f"导入命令失败: {err}"
        assert "导入完成" in out, f"未找到导入完成消息, 输出: {out}"
        print("✓ test_import_repository passed")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_stats_with_data():
    """测试有数据的统计"""
    code, out, err = run_command(f"python main.py stats --knowledge_base {TEST_KB_NAME}")
    assert code == 0, f"统计命令失败: {err}"
    # 应该有 2 个文件（hello.c 和 util.c）
    assert "总文件数: 2" in out, f"统计数据不正确, 输出: {out}"
    print("✓ test_stats_with_data passed")


def test_search_code():
    """测试代码搜索"""
    code, out, err = run_command(
        f'python main.py search "printf" --knowledge_base {TEST_KB_NAME} '
        f'--type code --limit 3'
    )
    assert code == 0, f"搜索命令失败: {err}"
    assert "找到" in out, f"未找到搜索结果, 输出: {out}"
    print("✓ test_search_code passed")


def test_search_with_filters():
    """测试带过滤器的搜索"""
    code, out, err = run_command(
        f'python main.py search "malloc" --knowledge_base {TEST_KB_NAME} '
        f'--type code --repo test_repo --limit 5'
    )
    assert code == 0, f"带过滤器的搜索失败: {err}"
    assert "找到" in out, f"未找到搜索结果, 输出: {out}"
    print("✓ test_search_with_filters passed")


def main():
    """运行所有测试"""
    print("测试 CLI 集成功能...")
    print("=" * 60)

    try:
        # 先清理旧数据
        cleanup()

        test_reset_database()
        test_stats_empty()
        test_import_repository()
        test_stats_with_data()
        test_search_code()
        test_search_with_filters()

        print("=" * 60)
        print("✓ 所有 CLI 集成测试通过！")
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
    finally:
        # 清理测试数据
        cleanup()


if __name__ == '__main__':
    exit(main())
