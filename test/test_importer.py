#!/usr/bin/env python3
"""Importer 单元测试"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evokb.io.importer import Importer
from evokb.knowledgebase import KnowledgeBase


def setup_test_env():
    temp_dir = tempfile.mkdtemp()
    db_path = tempfile.mktemp(suffix=".db")
    return temp_dir, db_path


def cleanup_test_env(temp_dir, db_path):
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    if os.path.exists(db_path):
        os.remove(db_path)


def test_import_directory():
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path, min_lines=0)
        importer = Importer(kb)

        with open(os.path.join(temp_dir, "test1.c"), "w", encoding="utf-8") as handle:
            handle.write("#include <stdio.h>\nint main() { return 0; }\n")
        with open(os.path.join(temp_dir, "Test.java"), "w", encoding="utf-8") as handle:
            handle.write(
                "class Test {\n"
                "    int value;\n"
                "    int getValue() { return value; }\n"
                "}\n"
            )

        importer.import_directory(temp_dir, "test_repo")

        records = kb.database.query(repository="test_repo")
        assert len(records) >= 3, f"应导入多个语义条目，实际 {len(records)}"
        print("✓ test_import_directory passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def test_import_empty_directory():
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path, min_lines=0)
        importer = Importer(kb)
        importer.import_directory(temp_dir, "test_repo")
        assert kb.database.query() == []
        print("✓ test_import_empty_directory passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def test_import_with_repository_name():
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path, min_lines=0)
        importer = Importer(kb)

        with open(os.path.join(temp_dir, "test.c"), "w", encoding="utf-8") as handle:
            handle.write("int main() { return 0; }\n")

        importer.import_directory(temp_dir, "my_test_repo")

        records = kb.database.query(repository="my_test_repo")
        assert records, "应按仓库名导入条目"
        assert all(record.repository == "my_test_repo" for record in records)
        print("✓ test_import_with_repository_name passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def test_import_nested_directory():
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path, min_lines=0)
        importer = Importer(kb)

        os.makedirs(os.path.join(temp_dir, "subdir"))
        with open(os.path.join(temp_dir, "test1.c"), "w", encoding="utf-8") as handle:
            handle.write("int main() { return 0; }\n")
        with open(os.path.join(temp_dir, "subdir", "test2.c"), "w", encoding="utf-8") as handle:
            handle.write("int foo() { return 1; }\n")

        importer.import_directory(temp_dir, "test_repo")
        records = kb.database.query(repository="test_repo")
        paths = {record.relative_path for record in records}
        assert "test1.c" in paths
        assert "subdir/test2.c" in paths
        print("✓ test_import_nested_directory passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def test_import_ignores_non_source_files():
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path, min_lines=0)
        importer = Importer(kb)

        with open(os.path.join(temp_dir, "test.c"), "w", encoding="utf-8") as handle:
            handle.write("int main() { return 0; }\n")
        with open(os.path.join(temp_dir, "readme.txt"), "w", encoding="utf-8") as handle:
            handle.write("This is a readme file.\n")
        with open(os.path.join(temp_dir, "notes.md"), "w", encoding="utf-8") as handle:
            handle.write("# Notes\nSome notes.\n")
        with open(os.path.join(temp_dir, "data.json"), "w", encoding="utf-8") as handle:
            handle.write('{"key": "value"}\n')

        importer.import_directory(temp_dir, "test_repo")

        records = kb.database.query(repository="test_repo")
        assert records, "应至少导入 .c 文件"
        extensions = {r.file_extension for r in records}
        assert ".txt" not in extensions, ".txt 文件不应被导入"
        assert ".md" not in extensions, ".md 文件不应被导入"
        assert ".json" not in extensions, ".json 文件不应被导入"
        print("✓ test_import_ignores_non_source_files passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def test_import_zip_file():
    import zipfile as zf
    temp_dir, db_path = setup_test_env()
    try:
        kb = KnowledgeBase(db_path, min_lines=0)

        zip_path = os.path.join(temp_dir, "test_repo.zip")
        with zf.ZipFile(zip_path, "w") as archive:
            archive.writestr("test_repo/hello.c", "#include <stdio.h>\nint main() { return 0; }\n")
            archive.writestr("test_repo/util.c", "int add(int a, int b) { return a + b; }\n")

        with zf.ZipFile(zip_path, "r") as archive:
            supported_extensions = set(kb.config_manager.ext_to_language.keys())
            source_files = [
                path for path in archive.namelist()
                if os.path.splitext(path)[1] in supported_extensions and not path.endswith("/")
            ]
            repo_records = []
            for file_path in source_files:
                content = archive.read(file_path).decode("utf-8", errors="ignore")
                from pathlib import Path
                parts = Path(file_path).parts
                relative_path = str(Path(*parts[1:])) if len(parts) > 1 else parts[0]
                records = kb.process_file_from_content(
                    content=content,
                    file_path=file_path,
                    repository="test_repo",
                    relative_path=relative_path,
                )
                repo_records.extend(records)
            kb.update_database_from_records(repo_records)

        db_records = kb.database.query(repository="test_repo")
        assert len(db_records) >= 2, f"zip 导入应至少生成 2 个条目，实际 {len(db_records)}"
        names = {r.qualified_name for r in db_records}
        assert "main" in names, f"应包含 main 函数，实际 {names}"
        assert "add" in names, f"应包含 add 函数，实际 {names}"
        print("✓ test_import_zip_file passed")
    finally:
        cleanup_test_env(temp_dir, db_path)


def main():
    print("Testing Importer...")
    print("=" * 60)

    try:
        test_import_directory()
        test_import_empty_directory()
        test_import_with_repository_name()
        test_import_nested_directory()
        test_import_ignores_non_source_files()
        test_import_zip_file()

        print("=" * 60)
        print("✓ All Importer tests passed!")
        return 0
    except AssertionError as exc:
        print("=" * 60)
        print(f"✗ Test failed: {exc}")
        return 1
    except Exception as exc:
        print("=" * 60)
        print(f"✗ Unexpected error: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
