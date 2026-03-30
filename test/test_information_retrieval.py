#!/usr/bin/env python3
"""InformationRetrieval 单元测试"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evokb.fingerprint.text_generator import TextFingerprintGenerator
from evokb.retrieval.information_retrieval import InformationRetrieval
from evokb.storage.database import Database
from evokb.storage.models import SemanticRecord


def setup_test_db():
    return tempfile.mktemp(suffix=".db")


def cleanup_test_db(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)


def build_record(text, fp, **overrides):
    data = {
        "repository": "repo1",
        "relative_path": "src/test.c",
        "file_extension": ".c",
        "language": "C",
        "kind": "function",
        "node_type": "function_definition",
        "symbol_name": "item",
        "qualified_name": "item",
        "parent_qualified_name": None,
        "start_line": 1,
        "end_line": 3,
        "text": text,
        "structure_fingerprint": None,
        "text_fingerprint": json.dumps(fp),
    }
    data.update(overrides)
    return SemanticRecord(**data)


def insert_test_records(db, fp_gen):
    text1 = "/* allocate dynamic memory for a buffer */\nint *alloc_buffer(void) { return 0; }"
    text2 = "/* free allocated resources after use */\nvoid cleanup(void) {}"
    text3 = '/* print the output string to stdout */\nvoid print_msg(void) { puts("x"); }'
    records = [
        build_record(
            text1,
            fp_gen.generate(text1),
            symbol_name="alloc_buffer",
            qualified_name="alloc_buffer",
        ),
        build_record(
            text2,
            fp_gen.generate(text2),
            relative_path="src/free.c",
            symbol_name="cleanup",
            qualified_name="cleanup",
        ),
        build_record(
            text3,
            fp_gen.generate(text3),
            relative_path="src/print.c",
            symbol_name="print_msg",
            qualified_name="print_msg",
        ),
    ]
    for record in records:
        db.insert(record)
    return records


def test_empty_database():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        ir = InformationRetrieval(db, TextFingerprintGenerator())
        assert ir.retrieve("allocate memory", shots=3) == []
        print("✓ test_empty_database passed")
    finally:
        cleanup_test_db(db_path)


def test_empty_input():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        ir = InformationRetrieval(db, TextFingerprintGenerator())
        assert ir.retrieve("", shots=3) == []
        assert ir.retrieve("***", shots=3) == []
        print("✓ test_empty_input passed")
    finally:
        cleanup_test_db(db_path)


def test_normal_retrieval():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = TextFingerprintGenerator()
        ir = InformationRetrieval(db, fp_gen)
        insert_test_records(db, fp_gen)

        results = ir.retrieve("allocate dynamic memory for a buffer", shots=3)
        assert len(results) > 0
        assert results[0]["qualified_name"] == "alloc_buffer"
        assert results[0]["score"] > 0
        assert 0.0 <= results[0]["containment"] <= 1.0
        assert "kind" in results[0]
        print("✓ test_normal_retrieval passed")
    finally:
        cleanup_test_db(db_path)


def test_shots_limit():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = TextFingerprintGenerator()
        ir = InformationRetrieval(db, fp_gen)
        insert_test_records(db, fp_gen)

        assert len(ir.retrieve("allocate dynamic memory for a buffer", shots=1)) == 1
        assert len(ir.retrieve("allocate dynamic memory for a buffer", shots=2)) == 2
        print("✓ test_shots_limit passed")
    finally:
        cleanup_test_db(db_path)


def test_get_coverage():
    ir = InformationRetrieval.__new__(InformationRetrieval)
    assert ir._get_coverage([1, 2, 3], [1, 2, 3]) == 1.0
    assert abs(ir._get_coverage([1, 2], [1, 2, 3]) - 2.0 / 3.0) < 1e-9
    assert ir._get_coverage([4, 5], [1, 2, 3]) == 0.0
    assert ir._get_coverage([1, 2], []) == 0.0
    print("✓ test_get_coverage passed")


def test_update_tree():
    ir = InformationRetrieval.__new__(InformationRetrieval)
    assert set(ir._update_tree([1, 2], [1, 2, 3, 4])) == {3, 4}
    assert set(ir._update_tree([5], [1, 2, 3])) == {1, 2, 3}
    print("✓ test_update_tree passed")


def test_language_filter():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = TextFingerprintGenerator()
        ir = InformationRetrieval(db, fp_gen)

        db.insert(
            build_record(
                "allocate dynamic memory buffer for data",
                fp_gen.generate("allocate dynamic memory buffer for data"),
                language="C",
            )
        )
        db.insert(
            build_record(
                "allocate dynamic memory buffer for data",
                fp_gen.generate("allocate dynamic memory buffer for data"),
                relative_path="pkg/AllocBuffer.java",
                file_extension=".java",
                language="Java",
                kind="type",
                node_type="class_declaration",
                symbol_name="AllocBuffer",
                qualified_name="AllocBuffer",
            )
        )

        results_c = ir.retrieve("allocate dynamic memory buffer for data", language="C", shots=5)
        results_java = ir.retrieve("allocate dynamic memory buffer for data", language="Java", shots=5)
        assert all(result["language"] == "C" for result in results_c)
        assert all(result["language"] == "Java" for result in results_java)
        print("✓ test_language_filter passed")
    finally:
        cleanup_test_db(db_path)


def test_max_prefilters_by_containment_before_greedy_retrieval():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = TextFingerprintGenerator()
        ir = InformationRetrieval(db, fp_gen)

        query = "zero one two three four five"
        db.insert(
            build_record(
                "zero one two three four five six",
                fp_gen.generate("zero one two three four five six"),
                relative_path="src/noise.c",
                symbol_name="noise",
                qualified_name="noise",
            )
        )
        db.insert(
            build_record(
                query,
                fp_gen.generate(query),
                relative_path="src/exact.c",
                symbol_name="exact",
                qualified_name="exact",
            )
        )

        results = ir.retrieve(query, shots=1, max_candidates=1)
        assert len(results) == 1
        assert results[0]["qualified_name"] == "exact"
        print("✓ test_max_prefilters_by_containment_before_greedy_retrieval passed")
    finally:
        cleanup_test_db(db_path)


def test_c_cpp_language_filter_interoperability():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = TextFingerprintGenerator()
        ir = InformationRetrieval(db, fp_gen)

        text = "allocate dynamic memory buffer for data"
        fp = fp_gen.generate(text)
        db.insert(
            build_record(
                text,
                fp,
                language="C",
                relative_path="src/buffer.c",
                symbol_name="buffer_c",
                qualified_name="buffer_c",
            )
        )
        db.insert(
            build_record(
                text,
                fp,
                language="C",
                file_extension=".hpp",
                relative_path="include/buffer.hpp",
                symbol_name="buffer_cpp",
                qualified_name="buffer_cpp",
            )
        )
        db.insert(
            build_record(
                text,
                fp,
                language="Java",
                file_extension=".java",
                relative_path="pkg/Buffer.java",
                kind="type",
                node_type="class_declaration",
                symbol_name="Buffer",
                qualified_name="Buffer",
            )
        )

        results_c = ir.retrieve(text, language="C", shots=5)
        results_cpp = ir.retrieve(text, language="C", shots=5)
        results_java = ir.retrieve(text, language="Java", shots=5)

        assert {result["language"] for result in results_c} == {"C", "C"}
        assert {result["language"] for result in results_cpp} == {"C", "C"}
        assert {result["language"] for result in results_java} == {"Java"}
        print("✓ test_c_cpp_language_filter_interoperability passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_many_empty_input():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        ir = InformationRetrieval(db, TextFingerprintGenerator())
        assert ir.retrieve_many([], shots=3) == []
        print("✓ test_retrieve_many_empty_input passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_many_matches_single_and_preserves_order():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = TextFingerprintGenerator()
        ir = InformationRetrieval(db, fp_gen)
        insert_test_records(db, fp_gen)

        queries = [
            "allocate dynamic memory for a buffer",
            "print the output string to stdout",
        ]

        expected = [ir.retrieve(query, shots=2) for query in queries]
        batch_results = ir.retrieve_many(queries, shots=2, max_workers=2)

        assert batch_results == expected
        print("✓ test_retrieve_many_matches_single_and_preserves_order passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_many_best_effort_for_invalid_inputs():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = TextFingerprintGenerator()
        ir = InformationRetrieval(db, fp_gen)
        insert_test_records(db, fp_gen)

        results = ir.retrieve_many(
            ["allocate dynamic memory for a buffer", "", "***"],
            shots=1,
            max_workers=2,
        )

        assert len(results) == 3
        assert results[0]
        assert results[1] == []
        assert results[2] == []
        print("✓ test_retrieve_many_best_effort_for_invalid_inputs passed")
    finally:
        cleanup_test_db(db_path)


def test_retrieve_many_serial_matches_parallel():
    db_path = setup_test_db()
    try:
        db = Database(db_path)
        fp_gen = TextFingerprintGenerator()
        ir = InformationRetrieval(db, fp_gen)
        insert_test_records(db, fp_gen)

        queries = [
            "allocate dynamic memory for a buffer",
            "free allocated resources after use",
            "print the output string to stdout",
        ]

        serial_results = ir.retrieve_many(queries, shots=2, max_workers=1)
        parallel_results = ir.retrieve_many(queries, shots=2, max_workers=2)
        assert serial_results == parallel_results
        print("✓ test_retrieve_many_serial_matches_parallel passed")
    finally:
        cleanup_test_db(db_path)


def test_prepare_skips_empty_fingerprint():
    from evokb.retrieval.information_retrieval import _prepare_information_candidates

    rows = [
        {
            "id": 1, "repository": "repo", "relative_path": "a.c",
            "language": "C", "kind": "function", "node_type": "function_definition",
            "symbol_name": "foo", "qualified_name": "foo",
            "parent_qualified_name": None, "start_line": 1, "end_line": 3,
            "text": "int foo() {}", "text_fingerprint": json.dumps([1, 2, 3]),
        },
        {
            "id": 2, "repository": "repo", "relative_path": "b.c",
            "language": "C", "kind": "function", "node_type": "function_definition",
            "symbol_name": "bar", "qualified_name": "bar",
            "parent_qualified_name": None, "start_line": 1, "end_line": 3,
            "text": "int bar() {}", "text_fingerprint": None,
        },
        {
            "id": 3, "repository": "repo", "relative_path": "c.c",
            "language": "C", "kind": "function", "node_type": "function_definition",
            "symbol_name": "baz", "qualified_name": "baz",
            "parent_qualified_name": None, "start_line": 1, "end_line": 3,
            "text": "int baz() {}", "text_fingerprint": "",
        },
    ]

    prepared = _prepare_information_candidates(rows, include_text=False, verbose=False)
    assert len(prepared) == 1, f"空/null 指纹应被过滤，实际保留 {len(prepared)}"
    assert prepared[0]["qualified_name"] == "foo"

    print("✓ test_prepare_skips_empty_fingerprint passed")


def main():
    print("Testing InformationRetrieval...")
    print("=" * 60)

    try:
        test_empty_database()
        test_empty_input()
        test_prepare_skips_empty_fingerprint()
        test_normal_retrieval()
        test_shots_limit()
        test_get_coverage()
        test_update_tree()
        test_language_filter()
        test_max_prefilters_by_containment_before_greedy_retrieval()
        test_c_cpp_language_filter_interoperability()
        test_retrieve_many_empty_input()
        test_retrieve_many_matches_single_and_preserves_order()
        test_retrieve_many_best_effort_for_invalid_inputs()
        test_retrieve_many_serial_matches_parallel()

        print("=" * 60)
        print("✓ All InformationRetrieval tests passed!")
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
