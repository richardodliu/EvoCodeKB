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

    # 测试 .h 扩展名（C/C++ 统一为 "C"）
    lang = config_mgr.get_language(".h")
    assert lang == "C", f"'.h' 应该映射到 'C'，实际是 '{lang}'"

    print("✓ test_ext_to_language passed")


def test_nonexistent_language():
    """测试不存在的语言"""
    config_mgr = ConfigManager()

    result = config_mgr.get_language(".nonexistent")
    assert result is None, "不存在的扩展名应该返回 None"

    print("✓ test_nonexistent_language passed")


def test_nonexistent_extension():
    """测试不存在的扩展名"""
    config_mgr = ConfigManager()

    result = config_mgr.get_language(".xyz")
    assert result is None, "不存在的扩展名应该返回 None"

    print("✓ test_nonexistent_extension passed")


def test_case_sensitivity():
    """测试大小写敏感性"""
    config_mgr = ConfigManager()

    # 测试小写扩展名
    lang1 = config_mgr.get_language(".c")
    # 测试大写扩展名
    lang2 = config_mgr.get_language(".C")

    # 配置中的扩展名是小写 ".c"，所以小写应该匹配成功
    assert lang1 == "C", f"'.c' 应该映射到 'C'，实际是 '{lang1}'"
    # 大写 ".C" 不在配置中，应该返回 None
    assert lang2 is None, f"'.C' 应该返回 None（大小写敏感），实际是 '{lang2}'"

    print("✓ test_case_sensitivity passed")


def test_multiple_extensions_same_language():
    """测试同一语言的多个扩展名"""
    config_mgr = ConfigManager()

    c_lang = config_mgr.get_language(".c")
    assert c_lang == "C", f".c 应该映射到 'C'，实际是 '{c_lang}'"

    cpp_exts = [".h", ".hpp", ".cc", ".cxx", ".hh"]
    for ext in cpp_exts:
        lang = config_mgr.get_language(ext)
        assert lang is not None, f"{ext} 应在配置中存在映射"
        assert lang == "C", f"{ext} 应该映射到 'C'，实际是 '{lang}'"

    print("✓ test_multiple_extensions_same_language passed")


def test_config_structure():
    """测试配置结构"""
    config_mgr = ConfigManager()

    languages = config_mgr.languages
    assert languages is not None, "languages 不应为 None"
    assert isinstance(languages, list), "配置应该是列表"
    assert len(languages) > 0, "至少应有一种语言配置"
    for lang in languages:
        assert "name" in lang, f"语言配置缺少 'name' 字段: {lang}"
        assert "extensions" in lang, f"语言配置缺少 'extensions' 字段: {lang}"
        assert isinstance(lang["extensions"], list), f"extensions 应为列表: {lang}"
        assert len(lang["extensions"]) > 0, f"语言 {lang['name']} 的 extensions 不应为空"

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
