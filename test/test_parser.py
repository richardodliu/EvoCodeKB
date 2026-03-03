#!/usr/bin/env python3
"""CodeParser 单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.parsing.parser import CodeParser


def test_parse_c_code():
    """测试 C 代码解析"""
    parser = CodeParser()
    code = """
    // This is a comment
    #include <stdio.h>
    /* Multi-line
       comment */
    int main() {
        printf("Hello"); // inline comment
        return 0;
    }
    """

    result = parser.parse(code, "C")
    assert result is not None, "解析结果不应为 None"
    assert isinstance(result, tuple), "结果应该是元组"
    assert len(result) == 2, "结果应该包含两个元素"

    code_part, comment_part = result
    assert isinstance(code_part, str), "代码应该是字符串"
    assert isinstance(comment_part, str), "注释应该是字符串"

    print("✓ test_parse_c_code passed")


def test_parse_python_code():
    """测试 Python 代码解析"""
    parser = CodeParser()
    code = """
    # This is a comment
    def hello():
        '''Docstring'''
        print("Hello")  # inline comment
        return 0
    """

    result = parser.parse(code, "Python")
    assert result is not None, "解析结果不应为 None"
    assert isinstance(result, tuple), "结果应该是元组"
    assert len(result) == 2, "结果应该包含两个元素"

    print("✓ test_parse_python_code passed")


def test_parse_empty_code():
    """测试空代码解析"""
    parser = CodeParser()
    result = parser.parse("", "C")

    assert result is not None, "空代码应该返回结果"
    code_part, comment_part = result
    # 空代码可能返回空字符串或包含空白字符
    assert isinstance(code_part, str), "代码部分应该是字符串"
    assert isinstance(comment_part, str), "注释部分应该是字符串"

    print("✓ test_parse_empty_code passed")


def test_parse_code_without_comments():
    """测试无注释代码"""
    parser = CodeParser()
    code = "int main() { return 0; }"

    result = parser.parse(code, "C")
    assert result is not None, "解析结果不应为 None"
    code_part, comment_part = result
    assert len(code_part) > 0, "应该有代码内容"

    print("✓ test_parse_code_without_comments passed")


def test_parse_multiline_comment():
    """测试多行注释"""
    parser = CodeParser()
    code = """
    /*
     * This is a multi-line comment
     * with multiple lines
     */
    int main() {
        return 0;
    }
    """

    result = parser.parse(code, "C")
    assert result is not None, "解析结果不应为 None"

    print("✓ test_parse_multiline_comment passed")


def test_parse_unsupported_language():
    """测试不支持的语言"""
    parser = CodeParser()
    code = "some code"

    result = parser.parse(code, "UnsupportedLanguage")
    # 不支持的语言应该返回原始代码
    assert result is not None, "应该返回某种结果"
    assert isinstance(result, tuple), "结果应该是元组"

    print("✓ test_parse_unsupported_language passed")


def test_get_lexer():
    """测试获取词法分析器"""
    parser = CodeParser()

    # 测试支持的语言
    lexer_c = parser._get_lexer("C")
    assert lexer_c is not None, "应该能获取 C 语言的词法分析器"

    lexer_py = parser._get_lexer("Python")
    assert lexer_py is not None, "应该能获取 Python 的词法分析器"

    print("✓ test_get_lexer passed")


def main():
    print("Testing CodeParser...")
    print("=" * 60)

    try:
        test_parse_c_code()
        test_parse_python_code()
        test_parse_empty_code()
        test_parse_code_without_comments()
        test_parse_multiline_comment()
        test_parse_unsupported_language()
        test_get_lexer()

        print("=" * 60)
        print("✓ All CodeParser tests passed!")
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
