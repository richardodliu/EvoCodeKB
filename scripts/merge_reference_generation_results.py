#!/usr/bin/env python3
"""Merge raw generation outputs and score EM/ES from saved predictions."""

from __future__ import annotations

import argparse
import csv
import json
import re
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
    "prompt_mode",
    "prompt_builder_requested",
    "prompt_extraction_mode_used",
    "docstring_found",
    "declaration_context_type",
    "local_context_lines_used",
    "stop_policy",
    "decode_policy",
    "beam_size",
    "prompt_context_line_count",
    "prompt_context_char_count",
    "prompt_context_token_count_full",
    "prompt_was_truncated_no_reference",
    "prompt_was_truncated_with_reference",
    "reference_shots_requested",
    "max_new_tokens_requested",
    "reference_candidates_total",
    "reference_candidates_considered",
    "reference_used_count",
    "reference_applied",
    "reference_partially_truncated",
    "reference_token_count",
    "reference_token_count_total_considered",
    "reference_budget_tokens_effective",
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
    "groundtruth_line_char_count",
    "groundtruth_token_count",
    "prediction_no_reference",
    "prediction_with_reference",
    "prediction_char_count_no_reference",
    "prediction_char_count_with_reference",
    "generated_token_count_no_reference",
    "generated_token_count_with_reference",
    "prediction_token_count_no_reference",
    "prediction_token_count_with_reference",
    "stop_reason_no_reference",
    "stop_reason_with_reference",
    "empty_prediction_no_reference",
    "empty_prediction_with_reference",
    "prompt_context_char_count",
    "prompt_context_line_count",
    "normalized_groundtruth",
    "normalized_prediction_no_reference",
    "normalized_prediction_with_reference",
    "em_no_reference",
    "em_with_reference",
    "em_improvement_abs",
    "es_no_reference",
    "es_with_reference",
    "es_improvement_abs",
    "strict_em_no_reference",
    "strict_em_with_reference",
    "strict_em_improvement_abs",
    "strict_es_no_reference",
    "strict_es_with_reference",
    "strict_es_improvement_abs",
    "comparison_status",
    "error",
]


GENERATION_POLICY = "single_line_generation"
STOP_BOUNDARY = "policy_controlled_single_line"
WHITESPACE_RE = re.compile(r"\s+")
TARGET_EM_NO_REFERENCE = 0.25
TARGET_ES_NO_REFERENCE = 0.5877


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
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


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _int_mean(records: list[dict[str, Any]], field: str) -> float | None:
    values = [_safe_int(record.get(field)) for record in records]
    return _mean([float(value) for value in values if value is not None])


def _normalize_line(text: Any) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" in text:
        return text.split("\n", 1)[0]
    return text


def _normalize_ignoring_whitespace(text: Any) -> str:
    return WHITESPACE_RE.sub("", _normalize_line(text))


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (char_a != char_b)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _edit_similarity(prediction: str, groundtruth: str) -> float:
    denominator = max(len(prediction), len(groundtruth))
    if denominator == 0:
        return 1.0
    distance = _levenshtein(prediction, groundtruth)
    return float(1.0 - (distance / denominator))


def _score_prediction(prediction: Any, groundtruth: str) -> dict[str, Any]:
    if prediction is None:
        return {
            "prediction_line": None,
            "normalized_prediction": None,
            "normalized_groundtruth": _normalize_ignoring_whitespace(groundtruth),
            "em": None,
            "es": None,
            "strict_em": None,
            "strict_es": None,
        }
    pred_line = _normalize_line(prediction)
    paper_pred = _normalize_ignoring_whitespace(pred_line)
    paper_gt = _normalize_ignoring_whitespace(groundtruth)
    return {
        "prediction_line": pred_line,
        "normalized_prediction": paper_pred,
        "normalized_groundtruth": paper_gt,
        "em": 1.0 if paper_pred == paper_gt else 0.0,
        "es": _edit_similarity(paper_pred, paper_gt),
        "strict_em": 1.0 if pred_line == groundtruth else 0.0,
        "strict_es": _edit_similarity(pred_line, groundtruth),
    }


def _score_record(record: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    scored = dict(record)
    groundtruth_line = _normalize_line(item.get("groundtruth", ""))
    scored["normalized_groundtruth"] = _normalize_ignoring_whitespace(groundtruth_line)

    no_ref_scores = _score_prediction(record.get("prediction_no_reference"), groundtruth_line)
    with_ref_scores = _score_prediction(record.get("prediction_with_reference"), groundtruth_line)

    scored["normalized_prediction_no_reference"] = no_ref_scores[
        "normalized_prediction"
    ]
    scored["normalized_prediction_with_reference"] = with_ref_scores[
        "normalized_prediction"
    ]

    scored["em_no_reference"] = no_ref_scores["em"]
    scored["es_no_reference"] = no_ref_scores["es"]
    scored["em_with_reference"] = with_ref_scores["em"]
    scored["es_with_reference"] = with_ref_scores["es"]

    scored["strict_em_no_reference"] = no_ref_scores["strict_em"]
    scored["strict_es_no_reference"] = no_ref_scores["strict_es"]
    scored["strict_em_with_reference"] = with_ref_scores["strict_em"]
    scored["strict_es_with_reference"] = with_ref_scores["strict_es"]

    if no_ref_scores["em"] is not None and with_ref_scores["em"] is not None:
        scored["em_improvement_abs"] = with_ref_scores["em"] - no_ref_scores["em"]
    else:
        scored["em_improvement_abs"] = None

    if no_ref_scores["es"] is not None and with_ref_scores["es"] is not None:
        scored["es_improvement_abs"] = with_ref_scores["es"] - no_ref_scores["es"]
    else:
        scored["es_improvement_abs"] = None

    if no_ref_scores["strict_em"] is not None and with_ref_scores["strict_em"] is not None:
        scored["strict_em_improvement_abs"] = (
            with_ref_scores["strict_em"] - no_ref_scores["strict_em"]
        )
    else:
        scored["strict_em_improvement_abs"] = None

    if no_ref_scores["strict_es"] is not None and with_ref_scores["strict_es"] is not None:
        scored["strict_es_improvement_abs"] = (
            with_ref_scores["strict_es"] - no_ref_scores["strict_es"]
        )
    else:
        scored["strict_es_improvement_abs"] = None

    return scored


def _applied_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("reference_applied")
        and _safe_float(record.get("em_with_reference")) is not None
        and _safe_float(record.get("es_with_reference")) is not None
    ]


def _valid_no_reference_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if _safe_float(record.get("em_no_reference")) is not None
        and _safe_float(record.get("es_no_reference")) is not None
    ]


def _build_summary(
    records: list[dict[str, Any]],
    input_path: Path,
    output_dir: Path,
    output_jsonl: Path,
    num_shards: int,
) -> dict[str, Any]:
    applied = _applied_records(records)
    valid_no_ref = _valid_no_reference_records(records)

    applied_em_no_ref = [
        _safe_float(record.get("em_no_reference"))
        for record in applied
        if _safe_float(record.get("em_no_reference")) is not None
    ]
    applied_em_with_ref = [
        _safe_float(record.get("em_with_reference"))
        for record in applied
        if _safe_float(record.get("em_with_reference")) is not None
    ]
    applied_es_no_ref = [
        _safe_float(record.get("es_no_reference"))
        for record in applied
        if _safe_float(record.get("es_no_reference")) is not None
    ]
    applied_es_with_ref = [
        _safe_float(record.get("es_with_reference"))
        for record in applied
        if _safe_float(record.get("es_with_reference")) is not None
    ]
    em_improvement_abs = [
        _safe_float(record.get("em_improvement_abs"))
        for record in applied
        if _safe_float(record.get("em_improvement_abs")) is not None
    ]
    es_improvement_abs = [
        _safe_float(record.get("es_improvement_abs"))
        for record in applied
        if _safe_float(record.get("es_improvement_abs")) is not None
    ]
    all_valid_em_no_ref = [
        _safe_float(record.get("em_no_reference"))
        for record in valid_no_ref
        if _safe_float(record.get("em_no_reference")) is not None
    ]
    all_valid_es_no_ref = [
        _safe_float(record.get("es_no_reference"))
        for record in valid_no_ref
        if _safe_float(record.get("es_no_reference")) is not None
    ]
    applied_strict_em_no_ref = [
        _safe_float(record.get("strict_em_no_reference"))
        for record in applied
        if _safe_float(record.get("strict_em_no_reference")) is not None
    ]
    applied_strict_em_with_ref = [
        _safe_float(record.get("strict_em_with_reference"))
        for record in applied
        if _safe_float(record.get("strict_em_with_reference")) is not None
    ]
    applied_strict_es_no_ref = [
        _safe_float(record.get("strict_es_no_reference"))
        for record in applied
        if _safe_float(record.get("strict_es_no_reference")) is not None
    ]
    applied_strict_es_with_ref = [
        _safe_float(record.get("strict_es_with_reference"))
        for record in applied
        if _safe_float(record.get("strict_es_with_reference")) is not None
    ]
    all_valid_strict_em_no_ref = [
        _safe_float(record.get("strict_em_no_reference"))
        for record in valid_no_ref
        if _safe_float(record.get("strict_em_no_reference")) is not None
    ]
    all_valid_strict_es_no_ref = [
        _safe_float(record.get("strict_es_no_reference"))
        for record in valid_no_ref
        if _safe_float(record.get("strict_es_no_reference")) is not None
    ]

    reference_shots = records[0].get("reference_shots_requested") if records else None
    max_new_tokens = records[0].get("max_new_tokens_requested") if records else None
    prompt_mode = records[0].get("prompt_mode") if records else None
    prompt_builder_requested = records[0].get("prompt_builder_requested") if records else None
    prompt_builder = records[0].get("prompt_extraction_mode_used") if records else None
    stop_policy = records[0].get("stop_policy") if records else None
    decode_policy = records[0].get("decode_policy") if records else None
    beam_size = records[0].get("beam_size") if records else None
    empty_prediction_rate_no_reference = _mean(
        [1.0 if record.get("empty_prediction_no_reference") else 0.0 for record in valid_no_ref]
    )
    empty_prediction_rate_with_reference = _mean(
        [1.0 if record.get("empty_prediction_with_reference") else 0.0 for record in applied]
    )
    prompt_extraction_fallback_rate = _mean(
        [
            1.0
            if "fallback" in str(record.get("prompt_extraction_mode_used", ""))
            else 0.0
            for record in valid_no_ref
        ]
    )
    docstring_found_rate = _mean(
        [1.0 if record.get("docstring_found") else 0.0 for record in valid_no_ref]
    )
    mean_em_no_reference = _mean(applied_em_no_ref)
    mean_es_no_reference = _mean(applied_es_no_ref)

    return {
        "input_path": str(input_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "output_jsonl": str(output_jsonl.resolve()),
        "num_shards": num_shards,
        "prompt_mode": prompt_mode,
        "prompt_builder_requested": prompt_builder_requested,
        "prompt_builder": prompt_builder,
        "stop_policy": stop_policy,
        "decode_policy": decode_policy,
        "beam_size": beam_size,
        "reference_shots": reference_shots,
        "max_new_tokens": max_new_tokens,
        "generation_policy": decode_policy or GENERATION_POLICY,
        "stop_boundary": stop_policy or STOP_BOUNDARY,
        "metric_definition_em": "exact match after removing all whitespace characters",
        "metric_definition_es": "edit similarity after removing all whitespace characters",
        "strict_metric_definition_em": "exact match on the first generated line",
        "strict_metric_definition_es": "edit similarity on the first generated line",
        "metric_scope": "reference_applied",
        "target_em_no_reference": TARGET_EM_NO_REFERENCE,
        "target_es_no_reference": TARGET_ES_NO_REFERENCE,
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
        "samples_runtime_error": sum(
            1 for record in records if record.get("comparison_status") == "runtime_error"
        ),
        "em_improved_count": sum(1 for value in em_improvement_abs if value is not None and value > 0),
        "em_worse_count": sum(1 for value in em_improvement_abs if value is not None and value < 0),
        "em_same_count": sum(1 for value in em_improvement_abs if value is not None and value == 0),
        "es_improved_count": sum(1 for value in es_improvement_abs if value is not None and value > 0),
        "es_worse_count": sum(1 for value in es_improvement_abs if value is not None and value < 0),
        "es_same_count": sum(1 for value in es_improvement_abs if value is not None and value == 0),
        "mean_em_no_reference": mean_em_no_reference,
        "median_em_no_reference": _median(applied_em_no_ref),
        "mean_em_with_reference": _mean(applied_em_with_ref),
        "median_em_with_reference": _median(applied_em_with_ref),
        "mean_es_no_reference": mean_es_no_reference,
        "median_es_no_reference": _median(applied_es_no_ref),
        "mean_es_with_reference": _mean(applied_es_with_ref),
        "median_es_with_reference": _median(applied_es_with_ref),
        "mean_em_improvement_abs": _mean(em_improvement_abs),
        "median_em_improvement_abs": _median(em_improvement_abs),
        "mean_es_improvement_abs": _mean(es_improvement_abs),
        "median_es_improvement_abs": _median(es_improvement_abs),
        "all_valid_mean_em_no_reference": _mean(all_valid_em_no_ref),
        "all_valid_median_em_no_reference": _median(all_valid_em_no_ref),
        "all_valid_mean_es_no_reference": _mean(all_valid_es_no_ref),
        "all_valid_median_es_no_reference": _median(all_valid_es_no_ref),
        "strict_mean_em_no_reference": _mean(applied_strict_em_no_ref),
        "strict_median_em_no_reference": _median(applied_strict_em_no_ref),
        "strict_mean_em_with_reference": _mean(applied_strict_em_with_ref),
        "strict_median_em_with_reference": _median(applied_strict_em_with_ref),
        "strict_mean_es_no_reference": _mean(applied_strict_es_no_ref),
        "strict_median_es_no_reference": _median(applied_strict_es_no_ref),
        "strict_mean_es_with_reference": _mean(applied_strict_es_with_ref),
        "strict_median_es_with_reference": _median(applied_strict_es_with_ref),
        "all_valid_strict_mean_em_no_reference": _mean(all_valid_strict_em_no_ref),
        "all_valid_strict_median_em_no_reference": _median(all_valid_strict_em_no_ref),
        "all_valid_strict_mean_es_no_reference": _mean(all_valid_strict_es_no_ref),
        "all_valid_strict_median_es_no_reference": _median(all_valid_strict_es_no_ref),
        "gap_to_target_em": (
            None
            if mean_em_no_reference is None
            else TARGET_EM_NO_REFERENCE - mean_em_no_reference
        ),
        "gap_to_target_es": (
            None
            if mean_es_no_reference is None
            else TARGET_ES_NO_REFERENCE - mean_es_no_reference
        ),
        "empty_prediction_rate_no_reference": empty_prediction_rate_no_reference,
        "empty_prediction_rate_with_reference": empty_prediction_rate_with_reference,
        "docstring_found_rate": docstring_found_rate,
        "prompt_extraction_fallback_rate": prompt_extraction_fallback_rate,
        "mean_groundtruth_token_count": _int_mean(valid_no_ref, "groundtruth_token_count"),
        "mean_reference_token_count": _int_mean(applied, "reference_token_count"),
        "mean_reference_used_count": _int_mean(applied, "reference_used_count"),
        "mean_prediction_token_count_no_reference": _int_mean(
            valid_no_ref, "prediction_token_count_no_reference"
        ),
        "mean_prediction_token_count_with_reference": _int_mean(
            applied, "prediction_token_count_with_reference"
        ),
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
        em_no_ref = [
            _safe_float(record.get("em_no_reference"))
            for record in applied
            if _safe_float(record.get("em_no_reference")) is not None
        ]
        em_with_ref = [
            _safe_float(record.get("em_with_reference"))
            for record in applied
            if _safe_float(record.get("em_with_reference")) is not None
        ]
        es_no_ref = [
            _safe_float(record.get("es_no_reference"))
            for record in applied
            if _safe_float(record.get("es_no_reference")) is not None
        ]
        es_with_ref = [
            _safe_float(record.get("es_with_reference"))
            for record in applied
            if _safe_float(record.get("es_with_reference")) is not None
        ]
        em_improvement_abs = [
            _safe_float(record.get("em_improvement_abs"))
            for record in applied
            if _safe_float(record.get("em_improvement_abs")) is not None
        ]
        es_improvement_abs = [
            _safe_float(record.get("es_improvement_abs"))
            for record in applied
            if _safe_float(record.get("es_improvement_abs")) is not None
        ]
        rows.append(
            {
                "repository": repository,
                "samples": len(repo_records),
                "applied_samples": len(applied),
                "mean_em_no_reference": _mean(em_no_ref),
                "mean_em_with_reference": _mean(em_with_ref),
                "mean_es_no_reference": _mean(es_no_ref),
                "mean_es_with_reference": _mean(es_with_ref),
                "mean_em_improvement_abs": _mean(em_improvement_abs),
                "mean_es_improvement_abs": _mean(es_improvement_abs),
            }
        )
    return rows


def _build_augmented_rows(
    input_path: Path,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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
            item["gen_eval"] = {key: record.get(key) for key in EVAL_KEYS}
            augmented_rows.append(item)
    return augmented_rows


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_jsonl = Path(args.output_jsonl)
    shard_paths = [
        output_dir / f"per_sample.rank{rank}.jsonl" for rank in range(args.num_shards)
    ]
    missing = [str(path) for path in shard_paths if not path.exists()]
    if missing:
        raise SystemExit(f"Missing shard outputs: {', '.join(missing)}")

    input_items: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                input_items.append(json.loads(line))

    merged_records: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()

    for shard_path in shard_paths:
        with shard_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                task_id = str(record.get("task_id"))
                if task_id in seen_task_ids:
                    raise SystemExit(f"Duplicate task_id detected while merging: {task_id}")
                seen_task_ids.add(task_id)
                sample_index = int(record.get("sample_index", 0))
                try:
                    item = input_items[sample_index]
                except IndexError as exc:
                    raise SystemExit(f"sample_index out of range while merging: {sample_index}") from exc
                merged_records.append(_score_record(record, item))

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
                "mean_em_no_reference",
                "mean_em_with_reference",
                "mean_es_no_reference",
                "mean_es_with_reference",
                "mean_em_improvement_abs",
                "mean_es_improvement_abs",
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
        description="Merge raw generation outputs and score EM/ES from saved predictions.",
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
