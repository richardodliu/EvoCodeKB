#!/usr/bin/env python3
"""测试 CLI 集成功能"""

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_KB_NAME = "test_cli"
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
TEST_DB_PATH = Path(PROJECT_ROOT) / "knowledgebase" / f"{TEST_KB_NAME}.db"

SAMPLE_FILES = {
    "test_repo/src/hello.c": """\
#include <stdio.h>

/* Print a greeting message */
int main() {
    printf("Hello, World!\\n");
    return 0;
}
""",
    "test_repo/src/util.c": """\
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
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    return result.returncode, result.stdout, result.stderr


def create_test_zip(tmp_dir):
    zip_path = os.path.join(tmp_dir, "test_repo.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for file_path, content in SAMPLE_FILES.items():
            zf.writestr(file_path, content)
    return tmp_dir


_data_imported = False


def _ensure_test_data():
    """确保测试数据已导入，避免测试间的隐式状态依赖。"""
    global _data_imported
    if _data_imported:
        return
    tmp_dir = tempfile.mkdtemp()
    try:
        data_dir = create_test_zip(tmp_dir)
        code, out, err = run_command(
            f"python main.py update --knowledge_path {data_dir} --knowledge_base {TEST_KB_NAME} --min_lines 0"
        )
        assert code == 0, f"测试数据导入失败: {err}"
        _data_imported = True
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def cleanup():
    global _data_imported
    _data_imported = False
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


def test_stats_empty():
    code, out, err = run_command(f"python main.py stats --knowledge_base {TEST_KB_NAME}")
    assert code == 0, f"统计命令失败: {err}"
    assert "总条目数: 0" in out, f"空数据库统计信息不正确, 输出: {out}"
    print("✓ test_stats_empty passed")


def test_import_repository():
    global _data_imported
    tmp_dir = tempfile.mkdtemp()
    try:
        data_dir = create_test_zip(tmp_dir)
        code, out, err = run_command(
            f"python main.py update --knowledge_path {data_dir} --knowledge_base {TEST_KB_NAME} --min_lines 0"
        )
        assert code == 0, f"导入命令失败: {err}"
        assert "导入完成" in out
        assert "总条目数" in out
        _data_imported = True
        print("✓ test_import_repository passed")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_stats_with_data():
    _ensure_test_data()
    code, out, err = run_command(f"python main.py stats --knowledge_base {TEST_KB_NAME}")
    assert code == 0, f"统计命令失败: {err}"
    assert "总条目数:" in out, f"输出中缺少总条目数, 输出: {out}"
    assert "总条目数: 0" not in out, f"导入后总条目数不应为 0, 输出: {out}"
    assert "function:" in out, f"应包含 function 类型统计, 输出: {out}"
    print("✓ test_stats_with_data passed")


def test_search_text():
    _ensure_test_data()
    code, out, err = run_command(
        f'python main.py search "printf" --knowledge_base {TEST_KB_NAME} --shots 3'
    )
    assert code == 0, f"搜索命令失败: {err}"
    assert "找到" in out
    assert "main" in out
    print("✓ test_search_text passed")


def test_search_with_kind_filter():
    _ensure_test_data()
    code, out, err = run_command(
        f'python main.py search "malloc" --knowledge_base {TEST_KB_NAME} --repo test_repo --kind function --shots 5'
    )
    assert code == 0, f"带过滤器的搜索失败: {err}"
    assert "my_strdup" in out
    assert "[function]" in out
    print("✓ test_search_with_kind_filter passed")


def main():
    print("测试 CLI 集成功能...")
    print("=" * 60)

    try:
        cleanup()
        test_stats_empty()
        test_import_repository()
        test_stats_with_data()
        test_search_text()
        test_search_with_kind_filter()

        print("=" * 60)
        print("✓ 所有 CLI 集成测试通过！")
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
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
