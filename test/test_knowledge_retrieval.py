#!/usr/bin/env python3
"""KnowledgeRetrieval 单元测试"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evokb.fingerprint.tree_generator import FingerprintTreeGenerator
from evokb.fingerprint.text_generator import TextFingerprintGenerator
from evokb.retrieval.knowledge_retrieval import KnowledgeRetrieval
from evokb.storage.database import Database
from evokb.storage.models import SemanticRecord


def setup_test_db():
    return tempfile.mktemp(suffix=".db")


def cleanup_test_db(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)


def build_record(text, fp, **overrides):
    text_fp = TextFingerprintGenerator().generate(text)
    data = {
        "repository": "test_repo",
        "relative_path": "src/test.c",
        "file_extension": ".c",
        "language": "C",
        "kind": "function",
        "node_type": "function_definition",
        "symbol_name": "foo",
        "qualified_name": "foo",
        "parent_qualified_name": None,
        "start_line": 1,
        "end_line": 3,
        "text": text,
        "structure_fingerprint": json.dumps(fp),
        "text_fingerprint": json.dumps(text_fp) if text_fp is not None else None,
    }
    data.update(overrides)
    return SemanticRecord(**data)


def test_get_coverage_calculation():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        retrieval = KnowledgeRetrieval(db, FingerprintTreeGenerator())

        assert retrieval._get_coverage([1, 2, 3], [1, 2, 3]) == 1.0
        assert retrieval._get_coverage([1, 2], [1, 2, 3, 4]) == 0.5
        assert retrieval._get_coverage([5, 6], [1, 2, 3]) == 0.0
        assert retrieval._get_coverage([1, 2], []) == 0.0
        print("✓ test_get_coverage_calculation passed")
    finally:
        cleanup_test_db(db_path)


def test_update_tree_logic():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        retrieval = KnowledgeRetrieval(db, FingerprintTreeGenerator())

        updated = retrieval._update_tree([1, 2, 3], [1, 2, 3, 4, 5])
        assert set(updated) == {4, 5}
        assert set(retrieval._update_tree([6], [1, 2, 3])) == {1, 2, 3}
        print("✓ test_update_tree_logic passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_empty_database():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        retrieval = KnowledgeRetrieval(db, FingerprintTreeGenerator())
        assert retrieval.retrieve("int main() { return 0; }", "C", shots=5) == []
        print("✓ test_retrieve_empty_database passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_normal_flow():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        code1 = "int main() { return 0; }"
        code2 = "int foo(int x) { return x + 1; }"
        fp1 = fp_gen.generate_fp_tree(code1, "C")
        fp2 = fp_gen.generate_fp_tree(code2, "C")

        db.insert(build_record(code1, fp1, symbol_name="main", qualified_name="main"))
        db.insert(build_record(code2, fp2, relative_path="src/test2.c", symbol_name="foo", qualified_name="foo"))

        results = retrieval.retrieve(code1, "C", shots=2)
        assert len(results) > 0
        assert results[0]["qualified_name"] == "main"
        assert results[0]["text"] == code1
        assert results[0]["score"] > 0
        assert results[0]["containment"] == 1.0
        assert "kind" in results[0]
        print("✓ test_retrieve_normal_flow passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_with_shots_limit():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        for index, code in enumerate(
            [
                "int f0() { return 0; }",
                "int f1(int x) { return x; }",
                "int f2(int a, int b) { return a + b; }",
            ]
        ):
            fp = fp_gen.generate_fp_tree(code, "C")
            db.insert(
                build_record(
                    code,
                    fp,
                    relative_path=f"src/test{index}.c",
                    symbol_name=f"f{index}",
                    qualified_name=f"f{index}",
                )
            )

        results = retrieval.retrieve("int main() { return 0; }", "C", shots=1)
        assert len(results) == 1
        print("✓ test_retrieve_with_shots_limit passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_prefers_declaration_block_on_tie():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        retrieval = KnowledgeRetrieval(db, FingerprintTreeGenerator())

        shared_fp = [1, 2, 3]
        db.insert(
            build_record(
                "int foo(int x) {\n    return x;\n}",
                shared_fp,
                kind="function",
                symbol_name="foo",
                qualified_name="foo",
                start_line=1,
                end_line=3,
            )
        )
        db.insert(
            build_record(
                "    int left = 1;\n    int right = 2;",
                shared_fp,
                kind="declaration_block",
                node_type="declaration_block",
                symbol_name="declblock#1",
                qualified_name="foo::declblock#1",
                parent_qualified_name="foo",
                start_line=2,
                end_line=3,
            )
        )

        results = retrieval.retrieve("int sum(int x) { return x; }", "C", shots=1)
        assert len(results) == 1
        assert results[0]["kind"] == "declaration_block"
        assert results[0]["qualified_name"] == "foo::declblock#1"
        assert "containment" in results[0]
        print("✓ test_retrieve_prefers_declaration_block_on_tie passed")
    finally:
        cleanup_test_db(db_path)


def test_containment_uses_structure_fingerprint():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        candidate_code = (
            "int foo(int x) {\n"
            "    int acc = x + 1;\n"
            "    return acc;\n"
            "}"
        )
        query_code = (
            "int bar(int y) {\n"
            "    int total = y + 1;\n"
            "    return total;\n"
            "}"
        )

        db.insert(
            build_record(
                candidate_code,
                fp_gen.generate_fp_tree(candidate_code, "C"),
                symbol_name="foo",
                qualified_name="foo",
            )
        )

        results = retrieval.retrieve(query_code, "C", shots=1)
        assert len(results) == 1
        assert results[0]["qualified_name"] == "foo"
        assert results[0]["containment"] == 1.0
        print("✓ test_containment_uses_structure_fingerprint passed")
    finally:
        cleanup_test_db(db_path)


def test_max_prefilters_by_containment_before_greedy_retrieval():
    class MockFingerprintGenerator:
        def generate_fp_tree(self, code, language):
            return [1, 2]

    db_path = setup_test_db()
    try:
        db = Database(db_path)
        retrieval = KnowledgeRetrieval(db, MockFingerprintGenerator())

        db.insert(
            build_record(
                "noise zero one two three four five six",
                [1, 2, 3],
                relative_path="src/noise.c",
                symbol_name="noise",
                qualified_name="noise",
            )
        )
        db.insert(
            build_record(
                "zero one two three four five",
                [1, 2],
                relative_path="src/exact.c",
                symbol_name="exact",
                qualified_name="exact",
            )
        )

        results = retrieval.retrieve(
            "zero one two three four five",
            "C",
            shots=1,
            max_candidates=1,
        )
        assert len(results) == 1
        assert results[0]["qualified_name"] == "exact"
        print("✓ test_max_prefilters_by_containment_before_greedy_retrieval passed")
    finally:
        cleanup_test_db(db_path)


def test_c_cpp_language_filter_interoperability():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        shared_code = "int add(int a, int b) { return a + b; }"
        shared_fp_c = fp_gen.generate_fp_tree(shared_code, "C")
        shared_fp_cpp = fp_gen.generate_fp_tree(shared_code, "C")

        db.insert(
            build_record(
                shared_code,
                shared_fp_c,
                language="C",
                relative_path="src/add.c",
                symbol_name="add_c",
                qualified_name="add_c",
            )
        )
        db.insert(
            build_record(
                shared_code,
                shared_fp_cpp,
                language="C",
                file_extension=".hpp",
                relative_path="include/add.hpp",
                symbol_name="add_cpp",
                qualified_name="add_cpp",
            )
        )
        db.insert(
            build_record(
                "class Add {\npublic:\n    int value() { return 1; }\n};",
                fp_gen.generate_fp_tree("class Add {\npublic:\n    int value() { return 1; }\n};", "Java"),
                language="Java",
                file_extension=".java",
                relative_path="pkg/Add.java",
                kind="type",
                node_type="class_declaration",
                symbol_name="Add",
                qualified_name="Add",
            )
        )

        results_c = retrieval.retrieve(shared_code, "C", shots=5)
        results_cpp = retrieval.retrieve(shared_code, "C", shots=5)

        assert "C" in {result["language"] for result in results_c}
        assert "C" in {result["language"] for result in results_cpp}
        assert "Java" not in {result["language"] for result in results_c}
        assert "Java" not in {result["language"] for result in results_cpp}
        print("✓ test_c_cpp_language_filter_interoperability passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_many_empty_input():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        retrieval = KnowledgeRetrieval(db, FingerprintTreeGenerator())
        assert retrieval.retrieve_many([], "C", shots=2) == []
        print("✓ test_retrieve_many_empty_input passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_many_matches_single_and_preserves_order():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        code1 = "int main() { return 0; }"
        code2 = "int add(int a, int b) { return a + b; }"
        code3 = "int mul(int a, int b) { return a * b; }"

        db.insert(build_record(code1, fp_gen.generate_fp_tree(code1, "C"), symbol_name="main", qualified_name="main"))
        db.insert(build_record(code2, fp_gen.generate_fp_tree(code2, "C"), relative_path="src/add.c", symbol_name="add", qualified_name="add"))
        db.insert(build_record(code3, fp_gen.generate_fp_tree(code3, "C"), relative_path="src/mul.c", symbol_name="mul", qualified_name="mul"))

        queries = [
            "int sum(int a, int b) { return a + b; }",
            "int product(int a, int b) { return a * b; }",
        ]

        expected = [retrieval.retrieve(query, "C", shots=2) for query in queries]
        batch_results = retrieval.retrieve_many(queries, "C", shots=2, max_workers=2)

        assert batch_results == expected
        print("✓ test_retrieve_many_matches_single_and_preserves_order passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_many_matches_single_for_mixed_inputs():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        code = "int add(int a, int b) { return a + b; }"
        db.insert(build_record(code, fp_gen.generate_fp_tree(code, "C"), symbol_name="add", qualified_name="add"))

        queries = [code, "", "%%%%"]
        expected = [retrieval.retrieve(query, "C", shots=1) for query in queries]
        results = retrieval.retrieve_many(
            queries,
            "C",
            shots=1,
            max_workers=2,
        )

        assert results == expected
        print("✓ test_retrieve_many_matches_single_for_mixed_inputs passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_shots_zero_returns_empty():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        code = "int add(int a, int b) { return a + b; }"
        db.insert(build_record(code, fp_gen.generate_fp_tree(code, "C")))

        results = retrieval.retrieve(code, "C", shots=0)
        assert results == [], f"shots=0 应返回空列表，实际 {len(results)} 条"
        print("✓ test_retrieve_shots_zero_returns_empty passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_shots_negative_returns_empty():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        code = "int add(int a, int b) { return a + b; }"
        db.insert(build_record(code, fp_gen.generate_fp_tree(code, "C")))

        results = retrieval.retrieve(code, "C", shots=-1)
        assert results == [], f"shots=-1 应返回空列表，实际 {len(results)} 条"
        print("✓ test_retrieve_shots_negative_returns_empty passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_many_serial_matches_parallel():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = FingerprintTreeGenerator()
        retrieval = KnowledgeRetrieval(db, fp_gen)

        records = [
            "int f0() { return 0; }",
            "int f1(int x) { return x + 1; }",
            "int f2(int x) { return x * 2; }",
        ]
        for index, code in enumerate(records):
            db.insert(
                build_record(
                    code,
                    fp_gen.generate_fp_tree(code, "C"),
                    relative_path=f"src/f{index}.c",
                    symbol_name=f"f{index}",
                    qualified_name=f"f{index}",
                )
            )

        queries = [
            "int inc(int x) { return x + 1; }",
            "int twice(int x) { return x * 2; }",
            "int zero() { return 0; }",
        ]

        serial_results = retrieval.retrieve_many(queries, "C", shots=2, max_workers=1)
        parallel_results = retrieval.retrieve_many(queries, "C", shots=2, max_workers=2)
        assert serial_results == parallel_results
        print("✓ test_retrieve_many_serial_matches_parallel passed")
    finally:
        cleanup_test_db(db_path)


def main():
    print("Testing KnowledgeRetrieval...")
    print("=" * 60)

    try:
        test_get_coverage_calculation()
        test_update_tree_logic()
        test_retrieve_empty_database()
        test_retrieve_normal_flow()
        test_retrieve_with_shots_limit()
        test_retrieve_prefers_declaration_block_on_tie()
        test_containment_uses_structure_fingerprint()
        test_max_prefilters_by_containment_before_greedy_retrieval()
        test_c_cpp_language_filter_interoperability()
        test_retrieve_many_empty_input()
        test_retrieve_many_matches_single_and_preserves_order()
        test_retrieve_many_matches_single_for_mixed_inputs()
        test_retrieve_shots_zero_returns_empty()
        test_retrieve_shots_negative_returns_empty()
        test_retrieve_many_serial_matches_parallel()

        print("=" * 60)
        print("✓ All KnowledgeRetrieval tests passed!")
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
