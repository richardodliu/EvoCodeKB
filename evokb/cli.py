#!/usr/bin/env python3
"""
代码知识库命令行入口

用法:
  evokb update --knowledge_path data/test --knowledge_base test [--min_lines 0]
  evokb stats --knowledge_base test
  evokb search "malloc" --knowledge_base test [--lang C] [--repo redis] [--kind function] [--shots 10]
  evokb knowledge_retrieve input.c --knowledge_base test [--shots 5] [--lang C]
  evokb information_retrieve input.txt --knowledge_base test [--shots 5] [--lang C]
"""

import argparse
import sys
import zipfile
from pathlib import Path

from .knowledgebase import KnowledgeBase

DB_DIR = Path("knowledgebase")


def get_db_path(db_name):
    """获取数据库路径。"""
    DB_DIR.mkdir(exist_ok=True)
    return DB_DIR / f"{db_name}.db"


def _format_location(result):
    return f"{result['relative_path']}:{result['start_line']}-{result['end_line']}"


def cmd_update(args):
    """从数据集目录构建/更新知识库。"""
    dataset_path = Path(args.knowledge_path)
    if not dataset_path.is_dir():
        print(f"错误: 数据集目录不存在: {dataset_path}", file=sys.stderr)
        sys.exit(1)
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path), min_lines=args.min_lines)
    supported_extensions = set(kb.config_manager.ext_to_language.keys())

    zip_files = sorted(dataset_path.glob("*.zip"))
    print(f"找到 {len(zip_files)} 个仓库压缩包\n")

    total_files = 0
    total_entries = 0
    total_success = 0
    total_error = 0

    for zip_file in zip_files:
        repo_name = zip_file.stem
        print(f"处理仓库: {repo_name}")

        try:
            with zipfile.ZipFile(zip_file, "r") as zf:
                source_files = [
                    path
                    for path in zf.namelist()
                    if Path(path).suffix in supported_extensions and not path.endswith("/")
                ]

                print(f"  找到 {len(source_files)} 个文件")
                total_files += len(source_files)

                file_tasks = []
                for file_path in source_files:
                    content = zf.read(file_path).decode("utf-8", errors="ignore")
                    parts = Path(file_path).parts
                    relative_path = str(Path(*parts[1:])) if len(parts) > 1 else parts[0]
                    file_tasks.append((content, file_path, repo_name, relative_path))

                repo_records, success_count, error_count, error_messages = (
                    kb.process_files_parallel(file_tasks, max_workers=args.workers)
                )
                entry_count = len(repo_records)
                for msg in error_messages[:3]:
                    print(f"    处理错误: {msg}")

                kb.update_database_from_records(repo_records)

                total_success += success_count
                total_error += error_count
                total_entries += entry_count

                print(
                    f"  ✓ {repo_name} 导入完成 "
                    f"(成功文件: {success_count}, 失败文件: {error_count}, 条目: {entry_count})\n"
                )
        except Exception as exc:
            print(f"  ✗ 无法处理 {zip_file}: {exc}\n")

    print("=" * 50)
    print("全部导入完成！")
    print(f"总文件数: {total_files}")
    print(f"总条目数: {total_entries}")
    print(f"成功文件: {total_success}")
    print(f"失败文件: {total_error}")
    print("=" * 50)

    stats = kb.get_stats()
    print("\n数据库统计:")
    print(f"  总条目数: {stats['total_entries']}")
    print(f"  按语言: {stats['by_language']}")
    print(f"  按仓库: {stats['by_repository']}")
    print(f"  按类型: {stats['by_kind']}")


def cmd_stats(args):
    """查看统计信息。"""
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path))
    stats = kb.get_stats()

    print(f"总条目数: {stats['total_entries']}")
    print("\n按语言:")
    for lang, count in stats["by_language"].items():
        print(f"  {lang}: {count}")
    print("\n按仓库:")
    for repo, count in stats["by_repository"].items():
        print(f"  {repo}: {count}")
    print("\n按类型:")
    for kind, count in stats["by_kind"].items():
        print(f"  {kind}: {count}")


def cmd_search(args):
    """搜索语义条目。"""
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path))
    results = kb.search_database(
        query=args.query,
        language=args.lang,
        repository=args.repo,
        kind=args.kind,
        shots=args.shots,
    )

    print(f"找到 {len(results)} 条匹配记录：\n")
    for result in results:
        location = _format_location(result)
        print(
            f"  [{result['kind']}] [{result['language']}] "
            f"{result['repository']} / {location}"
        )
        print(f"    {result['qualified_name']}")


def cmd_knowledge_retrieve(args):
    """检索相似结构条目。"""
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path))

    with open(args.input_file, "r", encoding="utf-8") as handle:
        input_code = handle.read()

    lang = args.lang
    if lang is None:
        ext = Path(args.input_file).suffix
        lang = kb.config_manager.get_language(ext)

    print(f"检索语言: {lang}")
    print(f"检索数量: {args.shots}")
    if args.limit > 0:
        print(f"预过滤候选: {args.limit}")
    if args.max > 0:
        print(f"相似度预过滤 top-max: {args.max}")
    if args.repo:
        print(f"限定仓库: {args.repo}")

    results = kb.knowledge_retrieve(
        input_code,
        lang,
        args.shots,
        args.repo,
        limit=args.limit,
        max_candidates=args.max,
    )

    print(f"\n找到 {len(results)} 个相似条目:\n")
    for index, result in enumerate(results, 1):
        location = _format_location(result)
        print(
            f"{index}. [{result['kind']}] [{result['language']}] "
            f"{result['repository']} / {location}"
        )
        print(f"   {result['qualified_name']}")
        print(f"   覆盖度: {result['score']:.4f}")
        print(f"   包含度: {result['containment']:.4f}")
        print()


def cmd_information_retrieve(args):
    """检索相关文本条目。"""
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path))

    with open(args.input_file, "r", encoding="utf-8") as handle:
        input_text = handle.read()

    print(f"检索数量: {args.shots}")
    if args.lang:
        print(f"检索语言: {args.lang}")
    if args.limit > 0:
        print(f"预过滤候选: {args.limit}")
    if args.max > 0:
        print(f"相似度预过滤 top-max: {args.max}")
    if args.repo:
        print(f"限定仓库: {args.repo}")

    results = kb.information_retrieve(
        input_text,
        args.lang,
        args.shots,
        args.repo,
        limit=args.limit,
        max_candidates=args.max,
    )

    print(f"\n找到 {len(results)} 个相关条目:\n")
    for index, result in enumerate(results, 1):
        location = _format_location(result)
        print(
            f"{index}. [{result['kind']}] [{result['language']}] "
            f"{result['repository']} / {location}"
        )
        print(f"   {result['qualified_name']}")
        print(f"   覆盖度: {result['score']:.4f}")
        print(f"   包含度: {result['containment']:.4f}")
        print()


def main():
    parser = argparse.ArgumentParser(description="代码知识库命令行工具")
    subparsers = parser.add_subparsers(dest="command")

    p_update = subparsers.add_parser("update", help="构建/更新知识库")
    p_update.add_argument("--knowledge_path", required=True, help="数据集目录路径（如 data/test）")
    p_update.add_argument("--knowledge_base", required=True, help="知识库名称（如 test）")
    p_update.add_argument(
        "--min_lines",
        type=int,
        default=0,
        help="strip 后文本行数小于等于该值时跳过入库（默认 0）",
    )
    p_update.add_argument(
        "--workers",
        type=int,
        default=None,
        help="并行处理进程数（默认 CPU 核心数，上限 8；设 1 为串行）",
    )
    p_update.set_defaults(func=cmd_update)

    p_stats = subparsers.add_parser("stats", help="查看统计信息")
    p_stats.add_argument("--knowledge_base", required=True, help="知识库名称")
    p_stats.set_defaults(func=cmd_stats)

    p_search = subparsers.add_parser("search", help="搜索语义条目")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument("--knowledge_base", required=True, help="知识库名称")
    p_search.add_argument("--lang", default=None, help="按语言过滤，如 C")
    p_search.add_argument("--repo", default=None, help="按仓库过滤")
    p_search.add_argument(
        "--kind",
        default=None,
        choices=[
            "global",
            "function",
            "method",
            "type",
            "declaration_block",
        ],
        help="按语义类型过滤",
    )
    p_search.add_argument("--shots", type=int, default=10, help="最多显示条数（默认 10）")
    p_search.set_defaults(func=cmd_search)

    p_retrieve = subparsers.add_parser("knowledge_retrieve", help="检索相似结构条目")
    p_retrieve.add_argument("input_file", help="输入代码文件路径")
    p_retrieve.add_argument("--knowledge_base", required=True, help="知识库名称")
    p_retrieve.add_argument("--shots", type=int, default=5, help="检索数量（默认 5）")
    p_retrieve.add_argument("--lang", default=None, help="按语言过滤，如 C")
    p_retrieve.add_argument("--repo", default=None, help="按仓库过滤")
    p_retrieve.add_argument(
        "--max",
        type=int,
        default=-1,
        help="先按 containment 预过滤 top-max 候选，再做贪心检索（默认 -1 不过滤）",
    )
    p_retrieve.add_argument(
        "--limit", type=int, default=-1, help="兼容旧参数：预过滤候选数量（默认 -1 不过滤）"
    )
    p_retrieve.set_defaults(func=cmd_knowledge_retrieve)

    p_info = subparsers.add_parser("information_retrieve", help="基于文本指纹检索相关条目")
    p_info.add_argument("input_file", help="输入文本文件路径")
    p_info.add_argument("--knowledge_base", required=True, help="知识库名称")
    p_info.add_argument("--shots", type=int, default=5, help="检索数量（默认 5）")
    p_info.add_argument("--lang", default=None, help="按语言过滤")
    p_info.add_argument("--repo", default=None, help="按仓库过滤")
    p_info.add_argument(
        "--max",
        type=int,
        default=-1,
        help="先按 containment 预过滤 top-max 候选，再做贪心检索（默认 -1 不过滤）",
    )
    p_info.add_argument(
        "--limit", type=int, default=-1, help="兼容旧参数：预过滤候选数量（默认 -1 不过滤）"
    )
    p_info.set_defaults(func=cmd_information_retrieve)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    raise SystemExit(main())
