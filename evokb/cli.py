#!/usr/bin/env python3
"""
代码知识库命令行入口

用法:
  evokb update --knowledge_path data/test --knowledge_base test
  evokb stats --knowledge_base test
  evokb search "malloc" --knowledge_base test [--type code] [--lang C] [--repo redis] [--limit 10]
  evokb knowledge_retrieve input.c --knowledge_base test [--shots 5] [--lang C]
  evokb information_retrieve input.txt --knowledge_base test [--shots 5] [--lang C]
"""

import argparse
import sys
import zipfile
from pathlib import Path
from .knowledgebase import KnowledgeBase

# 数据库统一存放在 knowledgebase/ 目录
DB_DIR = Path('knowledgebase')
DB_DIR.mkdir(exist_ok=True)


def get_db_path(db_name):
    """获取数据库路径"""
    return DB_DIR / f'{db_name}.db'


def cmd_update(args):
    """从数据集目录构建/更新知识库"""
    dataset_path = Path(args.knowledge_path)
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path))

    # 获取所有 zip 文件
    zip_files = sorted(dataset_path.glob('*.zip'))
    print(f"找到 {len(zip_files)} 个仓库压缩包\n")

    total_files = 0
    total_success = 0
    total_error = 0

    for zip_file in zip_files:
        repo_name = zip_file.stem  # 去掉 .zip 后缀
        print(f"处理仓库: {repo_name}")

        try:
            with zipfile.ZipFile(zip_file, 'r') as zf:
                # 获取所有 C 文件
                c_files = [f for f in zf.namelist()
                          if f.endswith(('.c', '.h')) and not f.endswith('/')]

                print(f"  找到 {len(c_files)} 个文件")
                total_files += len(c_files)

                success_count = 0
                error_count = 0

                for file_path in c_files:
                    try:
                        # 从 zip 中读取文件内容
                        content = zf.read(file_path).decode('utf-8', errors='ignore')

                        # 计算相对路径（去掉顶层目录）
                        parts = Path(file_path).parts
                        if len(parts) > 1:
                            relative_path = str(Path(*parts[1:]))
                        else:
                            relative_path = parts[0]

                        # 处理并保存
                        result = kb.process_file_from_content(
                            content=content,
                            file_path=file_path,
                            repository=repo_name,
                            relative_path=relative_path
                        )

                        kb.update_database_from_dict(result)
                        success_count += 1

                    except SyntaxError as e:
                        # 语法错误单独统计
                        error_count += 1
                        if error_count <= 5:  # 显示前5个语法错误
                            print(f"    语法错误: {relative_path}")
                    except Exception as e:
                        # 其他错误
                        error_count += 1
                        if error_count <= 3:
                            print(f"    处理错误: {relative_path}: {str(e)[:50]}")

                total_success += success_count
                total_error += error_count

                print(f"  ✓ {repo_name} 导入完成 (成功: {success_count}, 失败: {error_count})\n")

        except Exception as e:
            print(f"  ✗ 无法处理 {zip_file}: {e}\n")
            continue

    print(f"=" * 50)
    print(f"全部导入完成！")
    print(f"总文件数: {total_files}")
    print(f"成功: {total_success}")
    print(f"失败: {total_error} (包括语法错误)")
    print(f"=" * 50)

    stats = kb.get_stats()
    print(f"\n数据库统计:")
    print(f"  总记录数: {stats['total_files']}")
    print(f"  按语言: {stats['by_language']}")
    print(f"  按仓库: {stats['by_repository']}")


def cmd_stats(args):
    """查看统计信息"""
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path))
    stats = kb.get_stats()
    print(f"总文件数: {stats['total_files']}")
    print(f"\n按语言:")
    for lang, count in stats['by_language'].items():
        print(f"  {lang}: {count}")
    print(f"\n按仓库:")
    for repo, count in stats['by_repository'].items():
        print(f"  {repo}: {count}")


def cmd_search(args):
    """搜索代码库"""
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path))
    results = kb.search_database(
        query=args.query,
        search_type=args.type,
        language=args.lang,
        repository=args.repo,
    )

    total = len(results)
    shown = results[:args.limit]

    print(f"找到 {total} 条记录，显示前 {len(shown)} 条：\n")
    for r in shown:
        print(f"  [{r['language']}] {r['repository']} / {r['relative_path']}")


def cmd_knowledge_retrieve(args):
    """检索相似代码"""
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path))

    # 读取输入代码
    with open(args.input_file, 'r', encoding='utf-8') as f:
        input_code = f.read()

    # 推断语言
    lang = args.lang
    if lang is None:
        ext = Path(args.input_file).suffix
        lang = kb.config_manager.get_language(ext)

    print(f"检索语言: {lang}")
    print(f"检索数量: {args.shots}")
    if args.limit > 0:
        print(f"预过滤候选: {args.limit}")
    if args.repo:
        print(f"限定仓库: {args.repo}")

    # 执行检索
    results = kb.knowledge_retrieve(input_code, lang, args.shots, args.repo,
                                     limit=args.limit)

    print(f"\n找到 {len(results)} 个相似代码:\n")
    for i, result in enumerate(results, 1):
        print(f"{i}. [{result['language']}] {result['repository']} / {result['relative_path']}")
        print(f"   覆盖度: {result['score']:.4f}")
        print()


def cmd_information_retrieve(args):
    """基于注释指纹检索相关代码"""
    db_path = get_db_path(args.knowledge_base)
    kb = KnowledgeBase(str(db_path))

    # 读取输入文本
    with open(args.input_file, 'r', encoding='utf-8') as f:
        input_text = f.read()

    print(f"检索数量: {args.shots}")
    if args.lang:
        print(f"检索语言: {args.lang}")
    if args.limit > 0:
        print(f"预过滤候选: {args.limit}")
    if args.repo:
        print(f"限定仓库: {args.repo}")

    # 执行检索
    results = kb.information_retrieve(input_text, args.lang, args.shots, args.repo,
                                       limit=args.limit)

    print(f"\n找到 {len(results)} 个相关代码:\n")
    for i, result in enumerate(results, 1):
        print(f"{i}. [{result['language']}] {result['repository']} / {result['relative_path']}")
        print(f"   覆盖度: {result['score']:.4f}")
        print()


def main():
    parser = argparse.ArgumentParser(description='代码知识库命令行工具')
    subparsers = parser.add_subparsers(dest='command')

    # evokb update --knowledge_path data/test --knowledge_base test
    p_update = subparsers.add_parser('update', help='构建/更新知识库')
    p_update.add_argument('--knowledge_path', required=True, help='数据集目录路径（如 data/test）')
    p_update.add_argument('--knowledge_base', required=True, help='知识库名称（如 test）')
    p_update.set_defaults(func=cmd_update)

    # evokb stats --knowledge_base test
    p_stats = subparsers.add_parser('stats', help='查看统计信息')
    p_stats.add_argument('--knowledge_base', required=True, help='知识库名称')
    p_stats.set_defaults(func=cmd_stats)

    # evokb search "malloc" --knowledge_base test [--type code] [--lang C] [--repo redis] [--limit 10]
    p_search = subparsers.add_parser('search', help='搜索代码库')
    p_search.add_argument('query', help='搜索关键词')
    p_search.add_argument('--knowledge_base', required=True, help='知识库名称')
    p_search.add_argument('--type', default='all', choices=['all', 'code', 'comment', 'text'],
                          help='搜索范围（默认 all）')
    p_search.add_argument('--lang', default=None, help='按语言过滤，如 C')
    p_search.add_argument('--repo', default=None, help='按仓库过滤')
    p_search.add_argument('--limit', type=int, default=10, help='最多显示条数（默认 10）')
    p_search.set_defaults(func=cmd_search)

    # evokb knowledge_retrieve input.c --knowledge_base test [--shots 5] [--lang C]
    p_retrieve = subparsers.add_parser('knowledge_retrieve', help='检索相似代码')
    p_retrieve.add_argument('input_file', help='输入代码文件路径')
    p_retrieve.add_argument('--knowledge_base', required=True, help='知识库名称')
    p_retrieve.add_argument('--shots', type=int, default=5, help='检索数量（默认 5）')
    p_retrieve.add_argument('--lang', default=None, help='按语言过滤，如 C')
    p_retrieve.add_argument('--repo', default=None, help='按仓库过滤')
    p_retrieve.add_argument('--limit', type=int, default=-1,
                            help='预过滤候选数量（默认 -1 不过滤）')
    p_retrieve.set_defaults(func=cmd_knowledge_retrieve)

    # evokb information_retrieve input.txt --knowledge_base test [--shots 5] [--lang C]
    p_info = subparsers.add_parser('information_retrieve', help='基于注释指纹检索相关代码')
    p_info.add_argument('input_file', help='输入文本文件路径')
    p_info.add_argument('--knowledge_base', required=True, help='知识库名称')
    p_info.add_argument('--shots', type=int, default=5, help='检索数量（默认 5）')
    p_info.add_argument('--lang', default=None, help='按语言过滤')
    p_info.add_argument('--repo', default=None, help='按仓库过滤')
    p_info.add_argument('--limit', type=int, default=-1,
                         help='预过滤候选数量（默认 -1 不过滤）')
    p_info.set_defaults(func=cmd_information_retrieve)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
