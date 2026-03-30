#!/usr/bin/env python3
"""Merge per-shard reference log-PPL outputs into final summaries."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


EVAL_KEYS = [
    "sample_index",
    "task_id",
    "repository",
    "file",
    "shard_rank",
    "num_shards",
    "reference_shots_requested",
    "prompt_tail_lines_requested",
    "prompt_tail_line_count_observed",
    "prompt_tail_char_count",
    "prompt_tail_token_count_full",
    "prompt_was_truncated_no_reference",
    "prompt_was_truncated_with_reference",
    "reference_candidates_total",
    "reference_candidates_considered",
    "reference_used_count",
    "reference_applied",
    "reference_partially_truncated",
    "reference_token_count",
    "reference_token_count_total_considered",
    "reference_omitted_count",
    "reference_truncated_path",
    "reference_truncated_tokens_kept",
    "reference_truncated_tokens_total",
    "used_reference_paths",
    "omitted_reference_paths",
    "prompt_token_count_used_no_reference",
    "prompt_token_count_used_with_reference",
    "prefix_token_count_no_reference",
    "prefix_token_count_with_reference",
    "groundtruth_char_count",
    "groundtruth_token_count",
    "log_ppl_no_reference",
    "log_ppl_with_reference",
    "log_ppl_improvement_abs",
    "comparison_status",
    "error",
]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.fmean(values))


def _int_mean(records: list[dict[str, Any]], field: str) -> float | None:
    values = [_safe_int(record.get(field)) for record in records]
    return _mean([float(value) for value in values if value is not None])


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items()}


def _applied_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("reference_applied")
        and _safe_float(record.get("log_ppl_no_reference")) is not None
        and _safe_float(record.get("log_ppl_with_reference")) is not None
    ]


def _valid_no_reference_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if _safe_float(record.get("log_ppl_no_reference")) is not None]


def _build_summary(
    records: list[dict[str, Any]],
    input_path: Path,
    output_dir: Path,
    output_jsonl: Path,
    num_shards: int,
) -> dict[str, Any]:
    applied = _applied_records(records)
    valid_no_ref = _valid_no_reference_records(records)

    applied_no_ref = [
        _safe_float(record.get("log_ppl_no_reference"))
        for record in applied
        if _safe_float(record.get("log_ppl_no_reference")) is not None
    ]
    applied_with_ref = [
        _safe_float(record.get("log_ppl_with_reference"))
        for record in applied
        if _safe_float(record.get("log_ppl_with_reference")) is not None
    ]
    applied_improvement_abs = [
        _safe_float(record.get("log_ppl_improvement_abs"))
        for record in applied
        if _safe_float(record.get("log_ppl_improvement_abs")) is not None
    ]
    all_valid_no_ref = [
        _safe_float(record.get("log_ppl_no_reference"))
        for record in valid_no_ref
        if _safe_float(record.get("log_ppl_no_reference")) is not None
    ]

    reference_shots = records[0].get("reference_shots_requested") if records else None
    prompt_tail_lines = records[0].get("prompt_tail_lines_requested") if records else None

    return {
        "input_path": str(input_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "output_jsonl": str(output_jsonl.resolve()),
        "num_shards": num_shards,
        "reference_shots": reference_shots,
        "prompt_tail_lines": prompt_tail_lines,
        "metric_scope": "reference_applied",
        "samples_total": len(records),
        "samples_valid": len(valid_no_ref),
        "samples_with_reference_candidates": sum(
            1 for record in records if int(record.get("reference_candidates_considered", 0)) > 0
        ),
        "samples_with_reference_applied": len(applied),
        "samples_no_reference_candidates": sum(
            1 for record in records if record.get("comparison_status") == "no_reference_candidates"
        ),
        "samples_reference_budget_zero": sum(
            1 for record in records if record.get("comparison_status") == "reference_budget_zero"
        ),
        "samples_invalid_prompt_context": sum(
            1 for record in records if record.get("comparison_status") == "invalid_prompt_context"
        ),
        "samples_invalid_groundtruth": sum(
            1 for record in records if record.get("comparison_status") == "invalid_groundtruth"
        ),
        "samples_runtime_error": sum(
            1 for record in records if record.get("comparison_status") == "runtime_error"
        ),
        "improved_count": sum(1 for value in applied_improvement_abs if value > 0),
        "worse_count": sum(1 for value in applied_improvement_abs if value < 0),
        "same_count": sum(1 for value in applied_improvement_abs if value == 0),
        "mean_log_ppl_no_reference": _mean(applied_no_ref),
        "mean_log_ppl_with_reference": _mean(applied_with_ref),
        "mean_log_ppl_improvement_abs": _mean(applied_improvement_abs),
        "all_valid_mean_log_ppl_no_reference": _mean(all_valid_no_ref),
        "mean_groundtruth_token_count": _int_mean(valid_no_ref, "groundtruth_token_count"),
        "mean_prompt_tail_line_count_observed": _int_mean(valid_no_ref, "prompt_tail_line_count_observed"),
        "mean_prompt_tail_token_count_full": _int_mean(valid_no_ref, "prompt_tail_token_count_full"),
        "mean_prompt_token_count_used_no_reference": _int_mean(
            valid_no_ref, "prompt_token_count_used_no_reference"
        ),
        "mean_prompt_token_count_used_with_reference": _int_mean(
            applied, "prompt_token_count_used_with_reference"
        ),
        "mean_reference_token_count": _int_mean(applied, "reference_token_count"),
        "mean_reference_used_count": _int_mean(applied, "reference_used_count"),
    }


def _build_repository_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_repository: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        repository = record.get("repository") or "UNKNOWN"
        by_repository.setdefault(repository, []).append(record)

    rows: list[dict[str, Any]] = []
    for repository in sorted(by_repository):
        repo_records = by_repository[repository]
        applied = _applied_records(repo_records)
        applied_no_ref = [
            _safe_float(record.get("log_ppl_no_reference"))
            for record in applied
            if _safe_float(record.get("log_ppl_no_reference")) is not None
        ]
        applied_with_ref = [
            _safe_float(record.get("log_ppl_with_reference"))
            for record in applied
            if _safe_float(record.get("log_ppl_with_reference")) is not None
        ]
        improvement_abs = [
            _safe_float(record.get("log_ppl_improvement_abs"))
            for record in applied
            if _safe_float(record.get("log_ppl_improvement_abs")) is not None
        ]
        rows.append(
            {
                "repository": repository,
                "samples": len(repo_records),
                "applied_samples": len(applied),
                "mean_log_ppl_no_reference": _mean(applied_no_ref),
                "mean_log_ppl_with_reference": _mean(applied_with_ref),
                "mean_log_ppl_improvement_abs": _mean(improvement_abs),
                "improved_count": sum(1 for value in improvement_abs if value > 0),
                "mean_groundtruth_token_count": _int_mean(repo_records, "groundtruth_token_count"),
                "mean_reference_token_count": _int_mean(applied, "reference_token_count"),
                "mean_prompt_tail_token_count_full": _int_mean(repo_records, "prompt_tail_token_count_full"),
            }
        )
    return rows


def _build_augmented_rows(input_path: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records_by_index = {int(record["sample_index"]): record for record in records}
    augmented_rows: list[dict[str, Any]] = []

    with input_path.open("r", encoding="utf-8") as handle:
        for sample_index, line in enumerate(handle):
            if not line.strip():
                continue
            record = records_by_index.get(sample_index)
            if record is None:
                continue
            item = json.loads(line)
            item["log_ppl_eval"] = {key: record.get(key) for key in EVAL_KEYS}
            augmented_rows.append(item)
    return augmented_rows


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_jsonl = Path(args.output_jsonl)
    shard_paths = [output_dir / f"per_sample.rank{rank}.jsonl" for rank in range(args.num_shards)]
    missing = [str(path) for path in shard_paths if not path.exists()]
    if missing:
        raise SystemExit(f"Missing shard outputs: {', '.join(missing)}")

    merged_records: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()

    for shard_path in shard_paths:
        with shard_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = _normalize_record(json.loads(line))
                task_id = str(record.get("task_id"))
                if task_id in seen_task_ids:
                    raise SystemExit(f"Duplicate task_id detected while merging: {task_id}")
                seen_task_ids.add(task_id)
                merged_records.append(record)

    merged_records.sort(key=lambda record: int(record.get("sample_index", 0)))

    per_sample_path = output_dir / "per_sample.jsonl"
    with per_sample_path.open("w", encoding="utf-8") as handle:
        for record in merged_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = _build_summary(
        merged_records,
        input_path=input_path,
        output_dir=output_dir,
        output_jsonl=output_jsonl,
        num_shards=args.num_shards,
    )
    summary_path = output_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    repo_rows = _build_repository_rows(merged_records)
    csv_path = output_dir / "summary_by_repository.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "repository",
                "samples",
                "applied_samples",
                "mean_log_ppl_no_reference",
                "mean_log_ppl_with_reference",
                "mean_log_ppl_improvement_abs",
                "improved_count",
                "mean_groundtruth_token_count",
                "mean_reference_token_count",
                "mean_prompt_tail_token_count_full",
            ],
        )
        writer.writeheader()
        for row in repo_rows:
            writer.writerow(row)

    augmented_rows = _build_augmented_rows(input_path, merged_records)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as handle:
        for row in augmented_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    run_copy_path = output_dir / output_jsonl.name
    if run_copy_path.resolve() != output_jsonl.resolve():
        with run_copy_path.open("w", encoding="utf-8") as handle:
            for row in augmented_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        f"Merged {len(merged_records)} samples into {per_sample_path}; "
        f"summary={summary_path} repo_csv={csv_path} output_jsonl={output_jsonl}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge per-shard reference log-PPL outputs into final summaries.",
    )
    parser.add_argument("--input", required=True, help="Original input JSONL path")
    parser.add_argument("--output-dir", required=True, help="Output directory containing shard outputs")
    parser.add_argument("--output-jsonl", required=True, help="Final augmented JSONL path")
    parser.add_argument("--num-shards", type=int, required=True, help="Expected shard count")
    args = parser.parse_args()

    if args.num_shards <= 0:
        raise SystemExit("--num-shards must be > 0")

    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
