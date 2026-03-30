#!/usr/bin/env python3
"""对 JSONL 指定列的倒数 n 行做批量检索。"""

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evokb.knowledgebase import KnowledgeBase


DEFAULT_BATCH_SIZE = 1000


def _tail_lines(text, n):
    if text is None:
        return ""

    if not isinstance(text, str):
        text = str(text)

    lines = text.splitlines()
    if not lines:
        return ""

    return "\n".join(lines[-n:])


def _build_references(results):
    references = []
    for result in results:
        references.append(
            {
                "repository": result["repository"],
                "relative_path": result["relative_path"],
                "language": result["language"],
                "kind": result["kind"],
                "qualified_name": result["qualified_name"],
                "start_line": result["start_line"],
                "end_line": result["end_line"],
                "text": result["text"],
                "score": result["score"],
                "containment": result["containment"],
            }
        )
    return references


def _resolve_db_path(knowledge_base):
    db_name = knowledge_base
    if not db_name.endswith(".db"):
        db_name = f"{db_name}.db"
    return ROOT / "knowledgebase" / db_name


def run(args):
    db_path = _resolve_db_path(args.knowledge_base)
    if not db_path.exists():
        raise FileNotFoundError(f"知识库不存在: {db_path}")

    kb = KnowledgeBase(str(db_path))

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as handle:
        items = [json.loads(line) for line in handle]

    if args.limit > 0:
        items = items[:args.limit]

    total = len(items)
    print(f"读取输入: {input_path}", flush=True)
    print(f"知识库: {db_path}", flush=True)
    print(f"总条数: {total}", flush=True)
    print(f"检索模式: {args.mode}", flush=True)
    print(f"查询列: {args.query_column}", flush=True)
    print(f"倒数行数: {args.n}", flush=True)
    print(f"检索语言: {args.lang}", flush=True)
    print(f"shots: {args.shots}", flush=True)
    if args.limit > 0:
        print(f"处理前 {args.limit} 条输入", flush=True)
    if args.max > 0:
        print(f"containment top-max: {args.max}", flush=True)
    print(f"batch_size: {args.batch_size}", flush=True)
    print(f"max_workers: {args.max_workers if args.max_workers is not None else 'auto'}", flush=True)

    with output_path.open("w", encoding="utf-8") as out_handle:
        for batch_start in range(0, total, args.batch_size):
            batch_items = items[batch_start:batch_start + args.batch_size]
            queries = [
                _tail_lines(item.get(args.query_column, ""), args.n)
                for item in batch_items
            ]
            if args.mode == "knowledge":
                batch_results = kb.knowledge_retrieve_many(
                    queries,
                    args.lang,
                    shots=args.shots,
                    max_candidates=args.max,
                    max_workers=args.max_workers,
                )
            else:
                batch_results = kb.information_retrieve_many(
                    queries,
                    language=args.lang,
                    shots=args.shots,
                    max_candidates=args.max,
                    max_workers=args.max_workers,
                )

            for item, query, results in zip(batch_items, queries, batch_results):
                output_item = dict(item)
                output_item["retrieval_mode"] = args.mode
                output_item["retrieval_query"] = query
                output_item["references"] = _build_references(results)
                out_handle.write(json.dumps(output_item, ensure_ascii=False) + "\n")

            # Flush every batch so long-running jobs expose incremental progress on disk.
            out_handle.flush()
            os.fsync(out_handle.fileno())

            processed = min(batch_start + len(batch_items), total)
            print(f"进度: {processed}/{total}", flush=True)

    print(f"输出已保存: {output_path}", flush=True)

    # 计算命中率
    with output_path.open("r", encoding="utf-8") as handle:
        output_items = [json.loads(line) for line in handle]

    hit = 0
    for task in output_items:
        gt = task.get("groundtruth", "")
        for ref in task.get("references", []):
            if gt and gt in ref.get("text", ""):
                hit += 1
                break

    total_out = len(output_items)
    rate = hit / total_out if total_out > 0 else 0.0
    print(f"\n命中率: {hit}/{total_out} = {rate:.4f}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="对 JSONL 指定列的倒数 n 行做批量检索")
    parser.add_argument("--input", required=True, help="输入 JSONL 路径")
    parser.add_argument("--output", required=True, help="输出 JSONL 路径")
    parser.add_argument(
        "--mode",
        choices=["knowledge", "information"],
        default="knowledge",
        help="检索模式，默认 knowledge",
    )
    parser.add_argument("--query_column", required=True, help="作为查询源的列名")
    parser.add_argument("--n", required=True, type=int, help="取倒数 n 行，必须大于 0")
    parser.add_argument("--limit", type=int, default=-1, help="最多处理输入文件前多少条，默认 -1 全部处理")
    parser.add_argument("--max", type=int, default=100, help="先按 containment 预过滤 top-max 候选，再做贪心检索")
    parser.add_argument("--shots", type=int, default=10, help="每条返回的检索数量，默认 10")
    parser.add_argument("--knowledge_base", default="train", help="知识库名称或 .db 文件名，默认 train")
    parser.add_argument("--lang", default="C", help="检索语言，默认 C")
    parser.add_argument("--batch_size", type=int, default=DEFAULT_BATCH_SIZE, help="批处理大小，默认 1000")
    parser.add_argument("--max_workers", type=int, default=None, help="并行进程数，默认自动")
    args = parser.parse_args()

    if args.n <= 0:
        raise ValueError("--n 必须大于 0")
    if args.batch_size <= 0:
        raise ValueError("--batch_size 必须大于 0")
    if args.max <= 0 and args.max != -1:
        raise ValueError("--max 必须大于 0，或使用 -1 表示不过滤")
    if args.max_workers is not None and args.max_workers <= 0:
        raise ValueError("--max_workers 必须大于 0")

    run(args)


if __name__ == "__main__":
    raise SystemExit(main())
