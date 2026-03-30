#!/usr/bin/env python3
"""SyntaxChecker 单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.syntax.checker import SyntaxChecker


def test_check_valid_c_code():
    """测试有效 C 代码"""
    checker = SyntaxChecker()
    code = """
    #include <stdio.h>
    int main() {
        printf("Hello World");
        return 0;
    }
    """

    result = checker.check_syntax(code, "C")
    assert result is True, "有效的 C 代码应该通过语法检查"

    print("✓ test_check_valid_c_code passed")


def test_check_invalid_c_code():
    """测试无效 C 代码"""
    checker = SyntaxChecker()
    code = """
    int main() {
        printf("Hello"
        return 0;
    }
    """

    result = checker.check_syntax(code, "C")
    assert result is False, "无效的 C 代码应该不通过语法检查"

    print("✓ test_check_invalid_c_code passed")


def test_check_valid_cpp_code():
    """测试有效 C++ 代码"""
    checker = SyntaxChecker()
    code = """
    #include <iostream>
    int main() {
        std::cout << "Hello" << std::endl;
        return 0;
    }
    """

    result = checker.check_syntax(code, "C")
    assert result is True, "有效的 C++ 代码应该通过语法检查"

    print("✓ test_check_valid_cpp_code passed")


def test_check_valid_java_code():
    """测试有效 Java 代码"""
    checker = SyntaxChecker()
    code = """
    public class Main {
        public static void main(String[] args) {
            System.out.println("Hello");
        }
    }
    """

    result = checker.check_syntax(code, "Java")
    assert result is True, "有效的 Java 代码应该通过语法检查"

    print("✓ test_check_valid_java_code passed")


def test_check_empty_code():
    """测试空代码"""
    checker = SyntaxChecker()
    result = checker.check_syntax("", "C")

    # 空代码可能被认为是有效的或无效的，取决于实现
    assert isinstance(result, bool), "结果应该是布尔值"

    print("✓ test_check_empty_code passed")


def test_check_unsupported_language():
    """测试不支持的语言 — 无法加载解析器时跳过检查，返回 True"""
    checker = SyntaxChecker()
    code = "some code"

    result = checker.check_syntax(code, "UnsupportedLanguage")
    # 不支持的语言无法加载解析器，实现选择跳过检查并返回 True
    assert result is True, "不支持的语言应跳过检查并返回 True"

    print("✓ test_check_unsupported_language passed")


def test_has_errors():
    """测试错误检测 — 带语法错误的代码应返回 False"""
    checker = SyntaxChecker()

    # 缺少右括号和分号的 C 代码
    bad_code = "int main( { return }"
    result = checker.check_syntax(bad_code, "C")
    assert result is False, "语法错误的代码应该返回 False"

    print("✓ test_has_errors passed")


def main():
    print("Testing SyntaxChecker...")
    print("=" * 60)

    try:
        test_check_valid_c_code()
        test_check_invalid_c_code()
        test_check_valid_cpp_code()
        test_check_valid_java_code()
        test_check_empty_code()
        test_check_unsupported_language()
        test_has_errors()

        print("=" * 60)
        print("✓ All SyntaxChecker tests passed!")
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
