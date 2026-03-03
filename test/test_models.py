#!/usr/bin/env python3
"""CodeRecord 模型单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evokb.storage.models import CodeRecord
from datetime import datetime


def test_code_record_creation():
    """测试创建 CodeRecord 实例"""
    record = CodeRecord(
        repository="test_repo",
        relative_path="test.c",
        text="int main() { return 0; }",
        code="int main() { return 0; }",
        comment="Test comment",
        file_extension=".c",
        language="C"
    )

    assert record.repository == "test_repo", "仓库名应该匹配"
    assert record.relative_path == "test.c", "相对路径应该匹配"
    assert record.text == "int main() { return 0; }", "文本应该匹配"
    assert record.code == "int main() { return 0; }", "代码应该匹配"
    assert record.comment == "Test comment", "注释应该匹配"
    assert record.file_extension == ".c", "文件扩展名应该匹配"
    assert record.language == "C", "语言应该匹配"
    assert record.code_fingerprint is None, "默认指纹应该是 None"
    assert record.comment_fingerprint is None, "默认注释指纹应该是 None"
    assert record.created_at is None, "默认创建时间应该是 None"
    assert record.id is None, "默认 ID 应该是 None"

    print("✓ test_code_record_creation passed")


def test_code_record_with_optional_fields():
    """测试带可选字段的 CodeRecord"""
    now = datetime.now()
    record = CodeRecord(
        repository="test_repo",
        relative_path="test.c",
        text="code",
        code="code",
        comment="",
        file_extension=".c",
        language="C",
        code_fingerprint="[1, 2, 3]",
        comment_fingerprint="[4, 5, 6]",
        created_at=now,
        id=123
    )

    assert record.code_fingerprint == "[1, 2, 3]", "指纹应该匹配"
    assert record.comment_fingerprint == "[4, 5, 6]", "注释指纹应该匹配"
    assert record.created_at == now, "创建时间应该匹配"
    assert record.id == 123, "ID 应该匹配"

    print("✓ test_code_record_with_optional_fields passed")


def test_to_dict():
    """测试 to_dict() 序列化"""
    record = CodeRecord(
        repository="test_repo",
        relative_path="test.c",
        text="code",
        code="code",
        comment="comment",
        file_extension=".c",
        language="C",
        id=1
    )

    data = record.to_dict()

    assert isinstance(data, dict), "结果应该是字典"
    assert data['repository'] == "test_repo", "仓库名应该匹配"
    assert data['relative_path'] == "test.c", "相对路径应该匹配"
    assert data['text'] == "code", "文本应该匹配"
    assert data['code'] == "code", "代码应该匹配"
    assert data['comment'] == "comment", "注释应该匹配"
    assert data['file_extension'] == ".c", "文件扩展名应该匹配"
    assert data['language'] == "C", "语言应该匹配"
    assert data['id'] == 1, "ID 应该匹配"
    assert 'comment_fingerprint' in data, "字典应包含 comment_fingerprint 键"
    assert data['comment_fingerprint'] is None, "未设置时 comment_fingerprint 应为 None"

    print("✓ test_to_dict passed")


def test_from_dict():
    """测试 from_dict() 反序列化"""
    data = {
        'repository': "test_repo",
        'relative_path': "test.c",
        'text': "code",
        'code': "code",
        'comment': "comment",
        'file_extension': ".c",
        'language': "C",
        'id': 1
    }

    record = CodeRecord.from_dict(data)

    assert isinstance(record, CodeRecord), "结果应该是 CodeRecord 实例"
    assert record.repository == "test_repo", "仓库名应该匹配"
    assert record.relative_path == "test.c", "相对路径应该匹配"
    assert record.text == "code", "文本应该匹配"
    assert record.code == "code", "代码应该匹配"
    assert record.comment == "comment", "注释应该匹配"
    assert record.file_extension == ".c", "文件扩展名应该匹配"
    assert record.language == "C", "语言应该匹配"
    assert record.id == 1, "ID 应该匹配"

    print("✓ test_from_dict passed")


def test_round_trip_conversion():
    """测试往返转换一致性"""
    original = CodeRecord(
        repository="test_repo",
        relative_path="test.c",
        text="code",
        code="code",
        comment="comment",
        file_extension=".c",
        language="C",
        comment_fingerprint="[10, 20, 30]",
        id=1
    )

    # 转换为字典
    data = original.to_dict()

    # 从字典恢复
    restored = CodeRecord.from_dict(data)

    # 验证一致性
    assert restored.repository == original.repository, "仓库名应该一致"
    assert restored.relative_path == original.relative_path, "相对路径应该一致"
    assert restored.text == original.text, "文本应该一致"
    assert restored.code == original.code, "代码应该一致"
    assert restored.comment == original.comment, "注释应该一致"
    assert restored.file_extension == original.file_extension, "文件扩展名应该一致"
    assert restored.language == original.language, "语言应该一致"
    assert restored.comment_fingerprint == original.comment_fingerprint, "注释指纹应该一致"
    assert restored.id == original.id, "ID 应该一致"

    print("✓ test_round_trip_conversion passed")


def test_empty_fields():
    """测试空字段处理"""
    record = CodeRecord(
        repository="",
        relative_path="",
        text="",
        code="",
        comment="",
        file_extension="",
        language=""
    )

    assert record.repository == "", "空仓库名应该被接受"
    assert record.text == "", "空文本应该被接受"
    assert record.code == "", "空代码应该被接受"

    print("✓ test_empty_fields passed")


def main():
    print("Testing CodeRecord...")
    print("=" * 60)

    try:
        test_code_record_creation()
        test_code_record_with_optional_fields()
        test_to_dict()
        test_from_dict()
        test_round_trip_conversion()
        test_empty_fields()

        print("=" * 60)
        print("✓ All CodeRecord tests passed!")
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
