#!/usr/bin/env python3
"""FingerprintTreeGenerator 单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.fingerprint.tree_generator import FingerprintTreeGenerator
from evokb import DEFAULT_RECURSION_LIMIT, ensure_runtime


def test_generate_fp_tree_valid_c_code():
    """测试有效 C 代码生成指纹树"""
    fp_gen = FingerprintTreeGenerator()
    code = """
    #include <stdio.h>
    int main() {
        printf("Hello World");
        return 0;
    }
    """
    result = fp_gen.generate_fp_tree(code, "C")
    assert result is not None, "应该成功生成指纹树"
    assert isinstance(result, list), "结果应该是列表"
    assert len(result) > 0, "指纹树不应为空"
    assert all(isinstance(x, int) for x in result), "所有元素应该是整数"
    print("✓ test_generate_fp_tree_valid_c_code passed")


def test_generate_fp_tree_empty_code():
    """测试空代码处理"""
    fp_gen = FingerprintTreeGenerator()
    result = fp_gen.generate_fp_tree("", "C")
    # 空代码可能返回 None、空列表或包含根节点的列表
    assert result is None or isinstance(result, list), "空代码应返回 None 或列表"
    print("✓ test_generate_fp_tree_empty_code passed")


def test_generate_fp_tree_unsupported_language():
    """测试不支持的语言"""
    fp_gen = FingerprintTreeGenerator()
    code = "some code"
    result = fp_gen.generate_fp_tree(code, "UnsupportedLang")
    assert result is None, "不支持的语言应返回 None"
    print("✓ test_generate_fp_tree_unsupported_language passed")


def test_hash_consistency():
    """测试哈希一致性 - 相同代码生成相同指纹"""
    fp_gen = FingerprintTreeGenerator()
    code = "int main() { return 0; }"

    result1 = fp_gen.generate_fp_tree(code, "C")
    result2 = fp_gen.generate_fp_tree(code, "C")

    assert result1 == result2, "相同代码应生成相同指纹树"
    print("✓ test_hash_consistency passed")


def test_different_code_different_fingerprint():
    """测试结构不同的代码生成不同指纹"""
    fp_gen = FingerprintTreeGenerator()
    code1 = "int main() { return 0; }"
    code2 = "int add(int a, int b) { return a + b; }"

    result1 = fp_gen.generate_fp_tree(code1, "C")
    result2 = fp_gen.generate_fp_tree(code2, "C")

    assert result1 is not None, "代码1应该生成指纹树"
    assert result2 is not None, "代码2应该生成指纹树"
    assert result1 != result2, "结构不同的代码应生成不同的指纹树"

    print("✓ test_different_code_different_fingerprint passed")


def test_parser_caching():
    """测试解析器缓存机制"""
    fp_gen = FingerprintTreeGenerator()

    # 第一次获取解析器
    parser1 = fp_gen.get_parser("C")
    assert parser1 is not None, "应该成功获取 C 解析器"

    # 第二次获取应该返回缓存的解析器
    parser2 = fp_gen.get_parser("C")
    assert parser1 is parser2, "应该返回缓存的解析器实例"
    print("✓ test_parser_caching passed")


def test_multiple_languages():
    """测试多种语言支持"""
    fp_gen = FingerprintTreeGenerator()

    test_cases = [
        ("C", "int main() { return 0; }"),
        ("C", "int main() { return 0; }"),
        ("Java", "class Main { public static void main(String[] args) {} }"),
    ]

    for lang, code in test_cases:
        result = fp_gen.generate_fp_tree(code, lang)
        assert result is not None, f"{lang} 应该成功生成指纹树"
        assert len(result) > 0, f"{lang} 指纹树不应为空"

    print("✓ test_multiple_languages passed")


def test_recursion_limit_configured():
    """测试调用 ensure_runtime 后提升 Python 递归上限"""
    ensure_runtime()
    assert (
        sys.getrecursionlimit() >= DEFAULT_RECURSION_LIMIT
    ), "调用 ensure_runtime() 后递归上限应该被提升"
    print("✓ test_recursion_limit_configured passed")


def main():
    print("Testing FingerprintTreeGenerator...")
    print("=" * 60)

    try:
        test_generate_fp_tree_valid_c_code()
        test_generate_fp_tree_empty_code()
        test_generate_fp_tree_unsupported_language()
        test_hash_consistency()
        test_different_code_different_fingerprint()
        test_parser_caching()
        test_multiple_languages()
        test_recursion_limit_configured()

        print("=" * 60)
        print("✓ All FingerprintTreeGenerator tests passed!")
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
