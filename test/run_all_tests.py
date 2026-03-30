#!/usr/bin/env python3
"""运行所有测试"""
import sys
import os

# 将项目根目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 所有测试文件
TEST_FILES = [
    'test/test_fingerprint_tree_generator.py',
    'test/test_text_fingerprint_generator.py',
    'test/test_knowledge_retrieval.py',
    'test/test_information_retrieval.py',
    'test/test_database.py',
    'test/test_models.py',
    'test/test_search_engine.py',
    'test/test_parser.py',
    'test/test_syntax_checker.py',
    'test/test_config_manager.py',
    'test/test_file_processor.py',
    'test/test_importer.py',
    'test/test_basic_integration.py',
    'test/test_cli_integration.py',
    'test/test_retrieval_integration.py',
]


def run_test_module(module_path):
    """运行单个测试模块

    Args:
        module_path: 测试模块路径

    Returns:
        int: 通过返回 0，失败返回 1
    """
    import importlib.util

    if not os.path.exists(module_path):
        print(f"✗ Test file not found: {module_path}")
        return 1

    try:
        spec = importlib.util.spec_from_file_location("test_module", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.main()
    except Exception as e:
        print(f"✗ Failed to run {module_path}: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """运行所有测试并输出汇总"""
    passed = []
    failed = []

    for test_file in TEST_FILES:
        print(f"\n{'='*70}")
        print(f"Running {test_file}")
        print('='*70)

        result = run_test_module(test_file)

        if result == 0:
            passed.append(test_file)
        else:
            failed.append(test_file)

    # 汇总
    total = len(passed) + len(failed)
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print('='*70)
    print(f"Total:  {total}")
    print(f"Passed: {len(passed)} ✓")
    print(f"Failed: {len(failed)} ✗")

    if passed:
        print(f"\n✓ Passed tests ({len(passed)}):")
        for f in passed:
            print(f"  ✓ {f}")

    if failed:
        print(f"\n✗ Failed tests ({len(failed)}):")
        for f in failed:
            print(f"  ✗ {f}")
        print("\n" + "="*70)
        print("Some tests failed. Please check the output above.")
        print("="*70)
        return 1

    print("\n" + "="*70)
    print("✓ All tests passed!")
    print("="*70)
    return 0


if __name__ == "__main__":
    exit(main())
