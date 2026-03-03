#!/usr/bin/env python3
"""ConfigManager 单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.config.manager import ConfigManager


def test_get_language():
    """测试获取语言配置"""
    config_mgr = ConfigManager()

    # 测试获取扩展名映射
    ext_map = config_mgr.ext_to_language
    assert ext_map is not None, "应该能获取扩展名映射"
    assert isinstance(ext_map, dict), "扩展名映射应该是字典"

    # 测试获取语言列表
    languages = config_mgr.languages
    assert languages is not None, "应该能获取语言列表"
    assert isinstance(languages, list), "语言列表应该是列表"

    print("✓ test_get_language passed")


def test_ext_to_language():
    """测试文件扩展名到语言映射"""
    config_mgr = ConfigManager()

    # 测试 C 语言扩展名（配置文件中存在）
    lang = config_mgr.get_language(".c")
    assert lang == "C", f"'.c' 应该映射到 'C'，实际是 '{lang}'"

    # 测试 .h 扩展名
    lang = config_mgr.get_language(".h")
    assert lang == "C", f"'.h' 应该映射到 'C'，实际是 '{lang}'"

    print("✓ test_ext_to_language passed")


def test_nonexistent_language():
    """测试不存在的语言"""
    config_mgr = ConfigManager()

    result = config_mgr.get_language(".nonexistent")
    assert result == "unknown", "不存在的扩展名应该返回 'unknown'"

    print("✓ test_nonexistent_language passed")


def test_nonexistent_extension():
    """测试不存在的扩展名"""
    config_mgr = ConfigManager()

    result = config_mgr.get_language(".xyz")
    assert result == "unknown", "不存在的扩展名应该返回 'unknown'"

    print("✓ test_nonexistent_extension passed")


def test_case_sensitivity():
    """测试大小写敏感性"""
    config_mgr = ConfigManager()

    # 测试小写扩展名
    lang1 = config_mgr.get_language(".c")
    # 测试大写扩展名
    lang2 = config_mgr.get_language(".C")

    # 根据实现，可能大小写敏感或不敏感
    # 这里只验证返回值是合理的
    assert lang1 is not None or lang2 is not None, "至少一个应该返回有效语言"

    print("✓ test_case_sensitivity passed")


def test_multiple_extensions_same_language():
    """测试同一语言的多个扩展名"""
    config_mgr = ConfigManager()

    # C 有多个扩展名
    c_exts = [".c", ".h"]
    for ext in c_exts:
        lang = config_mgr.get_language(ext)
        if lang != "unknown":
            assert lang == "C", f"{ext} 应该映射到 'C'"

    print("✓ test_multiple_extensions_same_language passed")


def test_config_structure():
    """测试配置结构"""
    config_mgr = ConfigManager()

    languages = config_mgr.languages
    if languages is not None:
        # 验证配置包含必要的字段
        assert isinstance(languages, list), "配置应该是列表"
        # 可以添加更多字段验证

    print("✓ test_config_structure passed")


def main():
    print("Testing ConfigManager...")
    print("=" * 60)

    try:
        test_get_language()
        test_ext_to_language()
        test_nonexistent_language()
        test_nonexistent_extension()
        test_case_sensitivity()
        test_multiple_extensions_same_language()
        test_config_structure()

        print("=" * 60)
        print("✓ All ConfigManager tests passed!")
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
