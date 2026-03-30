#!/usr/bin/env python3
"""TextFingerprintGenerator 单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.fingerprint.text_generator import TextFingerprintGenerator


def test_normal_text():
    """测试正常文本生成 N-gram 指纹列表"""
    gen = TextFingerprintGenerator(n=3)
    text = "this is a simple test comment for fingerprint"
    result = gen.generate(text)
    assert result is not None, "正常文本应返回指纹"
    assert isinstance(result, list), "结果应该是列表"
    assert len(result) > 1, "词数大于 n 应生成多个 gram"
    assert all(isinstance(x, int) for x in result), "所有元素应该是整数"
    print("✓ test_normal_text passed")


def test_short_text():
    """测试短文本（词数 < n）返回单元素列表"""
    gen = TextFingerprintGenerator(n=5)
    text = "short note"
    result = gen.generate(text)
    assert result is not None, "短文本应返回指纹"
    assert len(result) == 1, f"词数 < n 应返回单元素列表，实际 {len(result)}"
    print("✓ test_short_text passed")


def test_empty_text():
    """测试空文本返回 None"""
    gen = TextFingerprintGenerator()
    assert gen.generate("") is None, "空字符串应返回 None"
    assert gen.generate("   ") is None, "纯空白应返回 None"
    print("✓ test_empty_text passed")


def test_none_text():
    """测试 None 输入返回 None"""
    gen = TextFingerprintGenerator()
    assert gen.generate(None) is None, "None 应返回 None"
    print("✓ test_none_text passed")


def test_symbol_only_text():
    """测试纯符号文本返回 None"""
    gen = TextFingerprintGenerator()
    assert gen.generate("// ***") is None, "纯符号文本应返回 None"
    assert gen.generate("/* --- */") is None, "纯符号文本应返回 None"
    assert gen.generate("# ===") is None, "纯符号文本应返回 None"
    print("✓ test_symbol_only_text passed")


def test_hash_consistency():
    """测试哈希一致性：同输入 → 同输出"""
    gen = TextFingerprintGenerator()
    text = "this function allocates memory for the buffer"
    result1 = gen.generate(text)
    result2 = gen.generate(text)
    assert result1 == result2, "相同文本应生成相同指纹"
    print("✓ test_hash_consistency passed")


def test_different_texts_different_fingerprints():
    """测试不同文本生成不同指纹"""
    gen = TextFingerprintGenerator(n=3)
    text1 = "allocate memory for the input buffer"
    text2 = "free all resources after completion"
    result1 = gen.generate(text1)
    result2 = gen.generate(text2)
    assert result1 is not None and result2 is not None, "两段文本都应生成指纹"
    assert result1 != result2, "不同文本应生成不同指纹"
    print("✓ test_different_texts_different_fingerprints passed")


def test_default_n_value():
    """测试默认 n=3"""
    gen = TextFingerprintGenerator()
    assert gen.n == 3, f"默认 n 应为 3，实际 {gen.n}"
    # 刚好 3 个词 → 1 个 gram
    text = "one two three"
    result = gen.generate(text)
    assert result is not None, "3 个词应生成指纹"
    assert len(result) == 1, f"刚好 n 个词应返回 1 个 gram，实际 {len(result)}"
    print("✓ test_default_n_value passed")


def main():
    print("Testing TextFingerprintGenerator...")
    print("=" * 60)

    try:
        test_normal_text()
        test_short_text()
        test_empty_text()
        test_none_text()
        test_symbol_only_text()
        test_hash_consistency()
        test_different_texts_different_fingerprints()
        test_default_n_value()

        print("=" * 60)
        print("✓ All TextFingerprintGenerator tests passed!")
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
