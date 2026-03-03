#!/usr/bin/env python3
"""CommentFingerprintGenerator 单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.fingerprint.comment_generator import CommentFingerprintGenerator


def test_normal_comment():
    """测试正常注释生成 N-gram 指纹列表"""
    gen = CommentFingerprintGenerator(n=3)
    comment = "this is a simple test comment for fingerprint"
    result = gen.generate(comment)
    assert result is not None, "正常注释应返回指纹"
    assert isinstance(result, list), "结果应该是列表"
    assert len(result) > 1, "词数大于 n 应生成多个 gram"
    assert all(isinstance(x, int) for x in result), "所有元素应该是整数"
    print("✓ test_normal_comment passed")


def test_short_comment():
    """测试短注释（词数 < n）返回单元素列表"""
    gen = CommentFingerprintGenerator(n=5)
    comment = "short note"
    result = gen.generate(comment)
    assert result is not None, "短注释应返回指纹"
    assert len(result) == 1, f"词数 < n 应返回单元素列表，实际 {len(result)}"
    print("✓ test_short_comment passed")


def test_empty_comment():
    """测试空注释返回 None"""
    gen = CommentFingerprintGenerator()
    assert gen.generate("") is None, "空字符串应返回 None"
    assert gen.generate("   ") is None, "纯空白应返回 None"
    print("✓ test_empty_comment passed")


def test_none_comment():
    """测试 None 输入返回 None"""
    gen = CommentFingerprintGenerator()
    assert gen.generate(None) is None, "None 应返回 None"
    print("✓ test_none_comment passed")


def test_symbol_only_comment():
    """测试纯符号注释返回 None"""
    gen = CommentFingerprintGenerator()
    assert gen.generate("// ***") is None, "纯符号注释应返回 None"
    assert gen.generate("/* --- */") is None, "纯符号注释应返回 None"
    assert gen.generate("# ===") is None, "纯符号注释应返回 None"
    print("✓ test_symbol_only_comment passed")


def test_hash_consistency():
    """测试哈希一致性：同输入 → 同输出"""
    gen = CommentFingerprintGenerator()
    comment = "this function allocates memory for the buffer"
    result1 = gen.generate(comment)
    result2 = gen.generate(comment)
    assert result1 == result2, "相同注释应生成相同指纹"
    print("✓ test_hash_consistency passed")


def test_different_comments_different_fingerprints():
    """测试不同注释生成不同指纹"""
    gen = CommentFingerprintGenerator(n=3)
    comment1 = "allocate memory for the input buffer"
    comment2 = "free all resources after completion"
    result1 = gen.generate(comment1)
    result2 = gen.generate(comment2)
    assert result1 is not None and result2 is not None, "两个注释都应生成指纹"
    assert result1 != result2, "不同注释应生成不同指纹"
    print("✓ test_different_comments_different_fingerprints passed")


def test_default_n_value():
    """测试默认 n=5"""
    gen = CommentFingerprintGenerator()
    assert gen.n == 5, f"默认 n 应为 5，实际 {gen.n}"
    # 刚好 5 个词 → 1 个 gram
    comment = "one two three four five"
    result = gen.generate(comment)
    assert result is not None, "5 个词应生成指纹"
    assert len(result) == 1, f"刚好 n 个词应返回 1 个 gram，实际 {len(result)}"
    print("✓ test_default_n_value passed")


def main():
    print("Testing CommentFingerprintGenerator...")
    print("=" * 60)

    try:
        test_normal_comment()
        test_short_comment()
        test_empty_comment()
        test_none_comment()
        test_symbol_only_comment()
        test_hash_consistency()
        test_different_comments_different_fingerprints()
        test_default_n_value()

        print("=" * 60)
        print("✓ All CommentFingerprintGenerator tests passed!")
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
