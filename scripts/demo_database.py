#!/usr/bin/env python3
"""
Benchmark 流水线：构建知识库 + 检索参考代码

用法:
  python scripts/demo_database.py

流程:
  1. 从 data/train/ 的 zip 文件构建知识库 → knowledgebase/train.db（已存在则跳过）
  2. 读取 benchmark/input.jsonl，对每条数据检索 5 个参考代码
  3. 结果保存到 benchmark/output.jsonl
"""

import json
import sys
import os
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evokb.knowledgebase import KnowledgeBase

# 路径配置
DATA_DIR = Path('data/train')
DB_DIR = Path('knowledgebase')
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / 'train.db'
INPUT_PATH = Path('benchmark/input.jsonl')
OUTPUT_PATH = Path('benchmark/output.jsonl')


def build_knowledgebase():
    """从 data/train/ 的 zip 文件构建知识库"""
    if DB_PATH.exists():
        print(f"知识库已存在: {DB_PATH}，跳过构建")
        return KnowledgeBase(str(DB_PATH))

    print(f"构建知识库: {DB_PATH}")
    kb = KnowledgeBase(str(DB_PATH))

    zip_files = sorted(DATA_DIR.glob('*.zip'))
    print(f"找到 {len(zip_files)} 个仓库压缩包\n")

    total_success = 0
    total_error = 0

    for zip_file in zip_files:
        repo_name = zip_file.stem
        print(f"处理仓库: {repo_name}")

        try:
            with zipfile.ZipFile(zip_file, 'r') as zf:
                c_files = [f for f in zf.namelist()
                           if f.endswith(('.c', '.h')) and not f.endswith('/')]

                print(f"  找到 {len(c_files)} 个文件")
                success_count = 0
                error_count = 0

                for file_path in c_files:
                    try:
                        content = zf.read(file_path).decode('utf-8', errors='ignore')

                        parts = Path(file_path).parts
                        if len(parts) > 1:
                            relative_path = str(Path(*parts[1:]))
                        else:
                            relative_path = parts[0]

                        record = kb.process_file_from_content(
                            content=content,
                            file_path=file_path,
                            repository=repo_name,
                            relative_path=relative_path
                        )
                        kb.update_database_from_dict(record)
                        success_count += 1

                    except SyntaxError:
                        error_count += 1
                    except Exception as e:
                        error_count += 1
                        if error_count <= 3:
                            print(f"    处理错误: {file_path}: {str(e)[:50]}")

                total_success += success_count
                total_error += error_count
                print(f"  ✓ {repo_name} 导入完成 (成功: {success_count}, 失败: {error_count})")

        except Exception as e:
            print(f"  ✗ 无法处理 {zip_file}: {e}")

    print(f"\n{'=' * 50}")
    print(f"全部导入完成！成功: {total_success}, 失败: {total_error}")

    stats = kb.get_stats()
    print(f"数据库总记录数: {stats['total_files']}")
    print(f"按仓库: {stats['by_repository']}")
    print(f"{'=' * 50}\n")

    return kb


def run_benchmark(kb, limit=-1):
    """对 benchmark/input.jsonl 的每条数据检索 5 个参考代码，保存到 output.jsonl"""
    print(f"读取输入: {INPUT_PATH}")

    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    total = len(lines)
    print(f"共 {total} 条任务\n")

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as out_f:
        for i, line in enumerate(lines):
            item = json.loads(line)

            prompt = item['prompt']

            results = kb.knowledge_retrieve(prompt, 'C', shots=5,
                                             limit=limit)

            references = []
            for r in results:
                references.append({
                    'repository': r['repository'],
                    'relative_path': r['relative_path'],
                    'language': r['language'],
                    'code': r['code'],
                    'score': r['score'],
                })

            item['references'] = references
            out_f.write(json.dumps(item, ensure_ascii=False) + '\n')

            if (i + 1) % 100 == 0 or (i + 1) == total:
                print(f"  进度: {i + 1}/{total}")

    print(f"\n结果已保存: {OUTPUT_PATH}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Benchmark 流水线')
    parser.add_argument('--limit', type=int, default=-1,
                       help='预过滤候选数量（默认 -1 不过滤）')
    args = parser.parse_args()

    kb = build_knowledgebase()
    run_benchmark(kb, limit=args.limit)


if __name__ == '__main__':
    main()
