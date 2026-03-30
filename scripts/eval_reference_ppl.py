#!/usr/bin/env python3
"""Evaluate ground-truth perplexity with and without retrieved references."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import traceback
from pathlib import Path
from typing import Any


class SampleStatusError(Exception):
    """Expected per-sample validation failure."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _tail_lines(text: Any, line_count: int) -> dict[str, Any]:
    raw_text = _coerce_str(text)
    raw_lines = raw_text.splitlines(keepends=True)
    if not raw_lines:
        return {
            "text": "",
            "line_count": 0,
            "char_count": 0,
        }

    tail = raw_lines[-line_count:] if line_count > 0 else []
    tail_text = "".join(tail)
    return {
        "text": tail_text,
        "line_count": len(tail),
        "char_count": len(tail_text),
    }


def _reference_path(ref: dict[str, Any]) -> str:
    repository = _coerce_str(ref.get("repository"))
    relative_path = _coerce_str(ref.get("relative_path"))
    qualified_name = _coerce_str(ref.get("qualified_name"))

    if repository and relative_path:
        return f"{repository}/{relative_path}"
    if relative_path:
        return relative_path
    if repository:
        return repository
    if qualified_name:
        return qualified_name
    return "UNKNOWN"


def _reference_text(ref: dict[str, Any]) -> str:
    return _coerce_str(ref.get("text"))


def _encode(tokenizer: Any, text: str) -> list[int]:
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_attention_mask=False,
        return_token_type_ids=False,
        verbose=False,
    )
    return list(encoded["input_ids"])


def _encode_with_offsets(tokenizer: Any, text: str) -> tuple[list[int], list[tuple[int, int]]]:
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_attention_mask=False,
        return_token_type_ids=False,
        return_offsets_mapping=True,
        verbose=False,
    )
    input_ids = list(encoded["input_ids"])
    offsets = [(int(start), int(end)) for start, end in encoded["offset_mapping"]]
    return input_ids, offsets


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


def _int_mean(records: list[dict[str, Any]], field: str) -> float | None:
    values = [_safe_int(record.get(field)) for record in records]
    return _mean([float(value) for value in values if value is not None])


def _load_completed_task_ids(output_path: Path) -> set[str]:
    completed: set[str] = set()
    if not output_path.exists():
        return completed

    with output_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Failed to parse existing output line {line_number}: {exc}"
                ) from exc
            completed.add(str(record.get("task_id")))
    return completed


def _choose_torch_dtype(torch_module: Any) -> Any:
    if not torch_module.cuda.is_available():
        raise RuntimeError("CUDA is required to run eval_reference_ppl.py")
    if torch_module.cuda.is_bf16_supported():
        return torch_module.bfloat16
    return torch_module.float16


def _compute_groundtruth_log_ppl(
    torch_module: Any,
    model: Any,
    device: Any,
    input_token_ids: list[int],
    label_token_ids: list[int],
) -> float:
    input_ids = torch_module.tensor(
        [input_token_ids],
        dtype=torch_module.long,
        device=device,
    )
    labels = torch_module.tensor(
        [label_token_ids],
        dtype=torch_module.long,
        device=device,
    )

    with torch_module.inference_mode():
        logits = model(input_ids=input_ids).logits

    shift_logits = logits[:, :-1, :].contiguous()
    shift_labels = labels[:, 1:].contiguous()

    loss_fct = torch_module.nn.CrossEntropyLoss(ignore_index=-100, reduction="none")
    losses = loss_fct(
        shift_logits.view(-1, shift_logits.size(-1)),
        shift_labels.view(-1),
    )
    valid_mask = shift_labels.view(-1) != -100
    if int(valid_mask.sum().item()) == 0:
        raise SampleStatusError("invalid_groundtruth", "groundtruth has zero scored tokens")

    avg_nll = losses[valid_mask].mean().item()
    return float(avg_nll)


def _build_scored_sequence(
    tokenizer: Any,
    prefix_text: str,
    groundtruth_text: str,
    max_context_tokens: int,
) -> dict[str, Any]:
    full_text = prefix_text + groundtruth_text
    full_input_ids, full_offsets = _encode_with_offsets(tokenizer, full_text)
    target_start_char = len(prefix_text)
    groundtruth_token_count = sum(1 for _, end in full_offsets if end > target_start_char)
    if groundtruth_token_count == 0:
        raise SampleStatusError("invalid_groundtruth", "groundtruth has zero scored tokens")
    if groundtruth_token_count >= max_context_tokens:
        raise SampleStatusError(
            "invalid_groundtruth",
            "groundtruth exceeds max_context_tokens",
        )

    if len(full_input_ids) > max_context_tokens:
        input_ids = full_input_ids[-max_context_tokens:]
        offsets = full_offsets[-max_context_tokens:]
    else:
        input_ids = full_input_ids
        offsets = full_offsets

    prefix_token_count_full = sum(1 for _, end in full_offsets if end <= target_start_char)

    label_ids: list[int] = []
    prefix_token_count = 0
    scored_token_count = 0
    for token_id, (_, end) in zip(input_ids, offsets):
        if end > target_start_char:
            label_ids.append(token_id)
            scored_token_count += 1
        else:
            label_ids.append(-100)
            prefix_token_count += 1

    if scored_token_count != groundtruth_token_count:
        raise SampleStatusError(
            "invalid_groundtruth",
            "groundtruth tokens were truncated unexpectedly",
        )

    return {
        "input_ids": input_ids,
        "label_ids": label_ids,
        "offsets": offsets,
        "full_offsets": full_offsets,
        "target_start_char": target_start_char,
        "groundtruth_token_count": groundtruth_token_count,
        "prefix_token_count": prefix_token_count,
        "prefix_token_count_full": prefix_token_count_full,
    }


def _count_region_tokens(offsets: list[tuple[int, int]], region_start_char: int, region_end_char: int) -> int:
    return sum(
        1
        for _, end in offsets
        if end > region_start_char and end <= region_end_char
    )


def _build_with_reference_sequence(
    tokenizer: Any,
    prompt_tail_text: str,
    references: list[dict[str, Any]],
    groundtruth_text: str,
    max_context_tokens: int,
) -> dict[str, Any]:
    reference_paths = [_reference_path(ref) for ref in references]
    reference_texts = [_reference_text(ref) for ref in references]
    full_reference_text = "".join(reference_texts)
    full_prefix_text = full_reference_text + prompt_tail_text
    sequence = _build_scored_sequence(
        tokenizer=tokenizer,
        prefix_text=full_prefix_text,
        groundtruth_text=groundtruth_text,
        max_context_tokens=max_context_tokens,
    )

    full_offsets = sequence["full_offsets"]
    offsets = sequence["offsets"]
    prompt_start_char = len(full_reference_text)
    prompt_end_char = len(full_prefix_text)
    kept_char_start = offsets[0][0] if offsets else len(full_prefix_text + groundtruth_text)

    prompt_token_count_full = _count_region_tokens(full_offsets, prompt_start_char, prompt_end_char)
    prompt_token_count_used = _count_region_tokens(offsets, prompt_start_char, prompt_end_char)
    reference_token_total_considered = sum(1 for _, end in full_offsets if end <= prompt_start_char)
    reference_token_count = sequence["prefix_token_count"] - prompt_token_count_used

    used_reference_paths: list[str] = []
    omitted_reference_paths: list[str] = []
    reference_partially_truncated = False
    reference_truncated_path: str | None = None
    reference_truncated_tokens_kept = 0
    reference_truncated_tokens_total = 0

    ref_start_char = 0
    for path, text in zip(reference_paths, reference_texts):
        ref_end_char = ref_start_char + len(text)
        token_total = sum(1 for _, end in full_offsets if end <= ref_end_char and end > ref_start_char)
        if token_total == 0 or ref_end_char <= kept_char_start:
            omitted_reference_paths.append(path)
        elif ref_start_char < kept_char_start < ref_end_char:
            used_reference_paths.append(path)
            reference_partially_truncated = True
            reference_truncated_path = path
            reference_truncated_tokens_kept = sum(
                1
                for token_start, token_end in offsets
                if token_end > ref_start_char and token_start < ref_end_char
            )
            reference_truncated_tokens_total = token_total
        else:
            overlap_count = sum(
                1
                for token_start, token_end in offsets
                if token_end > ref_start_char and token_start < ref_end_char
            )
            if overlap_count > 0:
                used_reference_paths.append(path)
            else:
                omitted_reference_paths.append(path)
        ref_start_char = ref_end_char

    sequence.update(
        {
            "reference_token_count": reference_token_count,
            "reference_token_count_total_considered": reference_token_total_considered,
            "reference_used_count": len(used_reference_paths),
            "reference_applied": bool(used_reference_paths) or reference_token_count > 0,
            "reference_partially_truncated": reference_partially_truncated,
            "reference_omitted_count": len(omitted_reference_paths),
            "reference_truncated_path": reference_truncated_path,
            "reference_truncated_tokens_kept": reference_truncated_tokens_kept,
            "reference_truncated_tokens_total": reference_truncated_tokens_total,
            "used_reference_paths": used_reference_paths,
            "omitted_reference_paths": omitted_reference_paths,
            "prompt_token_count_used": prompt_token_count_used,
            "prompt_token_count_full": prompt_token_count_full,
            "prompt_was_truncated": prompt_token_count_used < prompt_token_count_full,
            "prefix_token_count_total": sequence["prefix_token_count"],
        }
    )
    return sequence


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


def _build_summary(records: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    applied = _applied_records(records)
    valid_no_ref = _valid_no_reference_records(records)

    applied_no_ref = [_safe_float(record.get("log_ppl_no_reference")) for record in applied]
    applied_with_ref = [_safe_float(record.get("log_ppl_with_reference")) for record in applied]
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

    return {
        "input_path": str(Path(args.input).resolve()),
        "output_dir": str(Path(args.output_dir).resolve()),
        "model_path": str(Path(args.model_path).resolve()),
        "reference_shots": args.reference_shots,
        "prompt_tail_lines": args.prompt_tail_lines,
        "max_context_tokens": args.max_context_tokens,
        "num_shards": args.num_shards,
        "shard_rank": args.shard_rank,
        "limit": args.limit,
        "resume": args.resume,
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
        "improved_count": sum(1 for value in applied_improvement_abs if value is not None and value > 0),
        "worse_count": sum(1 for value in applied_improvement_abs if value is not None and value < 0),
        "same_count": sum(1 for value in applied_improvement_abs if value is not None and value == 0),
        "mean_log_ppl_no_reference": _mean([value for value in applied_no_ref if value is not None]),
        "mean_log_ppl_with_reference": _mean([value for value in applied_with_ref if value is not None]),
        "mean_log_ppl_improvement_abs": _mean(applied_improvement_abs),
        "all_valid_mean_log_ppl_no_reference": _mean(all_valid_no_ref),
        "mean_groundtruth_token_count": _int_mean(valid_no_ref, "groundtruth_token_count"),
        "mean_prompt_tail_line_count_observed": _int_mean(valid_no_ref, "prompt_tail_line_count_observed"),
        "mean_prompt_tail_token_count_full": _int_mean(valid_no_ref, "prompt_tail_token_count_full"),
        "mean_prompt_token_count_used_no_reference": _int_mean(valid_no_ref, "prompt_token_count_used_no_reference"),
        "mean_prompt_token_count_used_with_reference": _int_mean(applied, "prompt_token_count_used_with_reference"),
        "mean_reference_token_count": _int_mean(applied, "reference_token_count"),
        "mean_reference_used_count": _int_mean(applied, "reference_used_count"),
    }


def _load_model_stack(model_path: str) -> tuple[Any, Any, Any, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch_dtype = _choose_torch_dtype(torch)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map="auto",
        torch_dtype=torch_dtype,
        local_files_only=True,
    )
    model.eval()
    device = next(model.parameters()).device
    return torch, tokenizer, model, device


def _base_result(item: dict[str, Any], sample_index: int, args: argparse.Namespace) -> dict[str, Any]:
    metadata = item.get("metadata", {})
    task_id = str(metadata.get("task_id", sample_index))
    references_all = item.get("references", []) or []
    references_considered = references_all[: args.reference_shots]

    return {
        "sample_index": sample_index,
        "task_id": task_id,
        "repository": metadata.get("repository"),
        "file": metadata.get("file"),
        "shard_rank": args.shard_rank,
        "num_shards": args.num_shards,
        "reference_shots_requested": args.reference_shots,
        "prompt_tail_lines_requested": args.prompt_tail_lines,
        "prompt_tail_line_count_observed": 0,
        "prompt_tail_char_count": 0,
        "prompt_tail_token_count_full": 0,
        "prompt_was_truncated_no_reference": False,
        "prompt_was_truncated_with_reference": False,
        "reference_candidates_total": len(references_all),
        "reference_candidates_considered": len(references_considered),
        "reference_used_count": 0,
        "reference_applied": False,
        "reference_partially_truncated": False,
        "reference_token_count": 0,
        "reference_token_count_total_considered": 0,
        "reference_omitted_count": 0,
        "reference_truncated_path": None,
        "reference_truncated_tokens_kept": 0,
        "reference_truncated_tokens_total": 0,
        "used_reference_paths": [],
        "omitted_reference_paths": [],
        "prompt_token_count_used_no_reference": 0,
        "prompt_token_count_used_with_reference": 0,
        "prefix_token_count_no_reference": 0,
        "prefix_token_count_with_reference": 0,
        "groundtruth_char_count": 0,
        "groundtruth_token_count": 0,
        "log_ppl_no_reference": None,
        "log_ppl_with_reference": None,
        "log_ppl_improvement_abs": None,
        "comparison_status": None,
        "error": None,
    }


def _evaluate_one(
    item: dict[str, Any],
    sample_index: int,
    args: argparse.Namespace,
    torch_module: Any,
    tokenizer: Any,
    model: Any,
    device: Any,
) -> dict[str, Any]:
    result = _base_result(item, sample_index, args)
    references = (item.get("references", []) or [])[: args.reference_shots]

    try:
        prompt_tail = _tail_lines(item.get("prompt", ""), args.prompt_tail_lines)
        prompt_tail_text = prompt_tail["text"]
        result["prompt_tail_line_count_observed"] = prompt_tail["line_count"]
        result["prompt_tail_char_count"] = prompt_tail["char_count"]
        if prompt_tail_text == "":
            raise SampleStatusError("invalid_prompt_context", "prompt tail is empty")

        groundtruth_text = _coerce_str(item.get("groundtruth", ""))
        result["groundtruth_char_count"] = len(groundtruth_text)

        no_ref = _build_scored_sequence(
            tokenizer=tokenizer,
            prefix_text=prompt_tail_text,
            groundtruth_text=groundtruth_text,
            max_context_tokens=args.max_context_tokens,
        )
        result["groundtruth_token_count"] = no_ref["groundtruth_token_count"]
        result["prompt_tail_token_count_full"] = no_ref["prefix_token_count_full"]
        result["prompt_token_count_used_no_reference"] = no_ref["prefix_token_count"]
        result["prefix_token_count_no_reference"] = no_ref["prefix_token_count"]
        result["prompt_was_truncated_no_reference"] = (
            no_ref["prefix_token_count"] < no_ref["prefix_token_count_full"]
        )
        result["log_ppl_no_reference"] = _compute_groundtruth_log_ppl(
            torch_module,
            model,
            device,
            no_ref["input_ids"],
            no_ref["label_ids"],
        )

        if not references:
            result["comparison_status"] = "no_reference_candidates"
            return result

        with_ref = _build_with_reference_sequence(
            tokenizer=tokenizer,
            prompt_tail_text=prompt_tail_text,
            references=references,
            groundtruth_text=groundtruth_text,
            max_context_tokens=args.max_context_tokens,
        )
        result["reference_token_count"] = with_ref["reference_token_count"]
        result["reference_token_count_total_considered"] = with_ref["reference_token_count_total_considered"]
        result["reference_used_count"] = with_ref["reference_used_count"]
        result["reference_applied"] = with_ref["reference_applied"]
        result["reference_partially_truncated"] = with_ref["reference_partially_truncated"]
        result["reference_omitted_count"] = with_ref["reference_omitted_count"]
        result["reference_truncated_path"] = with_ref["reference_truncated_path"]
        result["reference_truncated_tokens_kept"] = with_ref["reference_truncated_tokens_kept"]
        result["reference_truncated_tokens_total"] = with_ref["reference_truncated_tokens_total"]
        result["used_reference_paths"] = with_ref["used_reference_paths"]
        result["omitted_reference_paths"] = with_ref["omitted_reference_paths"]
        result["prompt_token_count_used_with_reference"] = with_ref["prompt_token_count_used"]
        result["prefix_token_count_with_reference"] = with_ref["prefix_token_count_total"]
        result["prompt_was_truncated_with_reference"] = with_ref["prompt_was_truncated"]

        if not with_ref["reference_applied"]:
            result["comparison_status"] = "reference_budget_zero"
            return result

        result["log_ppl_with_reference"] = _compute_groundtruth_log_ppl(
            torch_module,
            model,
            device,
            with_ref["input_ids"],
            with_ref["label_ids"],
        )
        result["log_ppl_improvement_abs"] = result["log_ppl_no_reference"] - result["log_ppl_with_reference"]
        result["comparison_status"] = "ok"
        return result
    except SampleStatusError as exc:
        result["comparison_status"] = exc.status
        result["error"] = exc.message
        return result
    except Exception as exc:
        result["comparison_status"] = "runtime_error"
        result["error"] = f"{exc}\n{traceback.format_exc()}"
        return result


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    per_sample_path = output_dir / f"per_sample.rank{args.shard_rank}.jsonl"
    summary_path = output_dir / f"summary.rank{args.shard_rank}.json"

    completed_task_ids = _load_completed_task_ids(per_sample_path) if args.resume else set()
    if completed_task_ids:
        print(
            f"[rank {args.shard_rank}] resuming with {len(completed_task_ids)} completed samples",
            flush=True,
        )

    torch_module, tokenizer, model, device = _load_model_stack(args.model_path)
    print(
        f"[rank {args.shard_rank}] model loaded on {device}; "
        f"input={input_path} output={per_sample_path} "
        f"prompt_tail_lines={args.prompt_tail_lines}",
        flush=True,
    )

    processed_records: list[dict[str, Any]] = []
    mode = "a" if args.resume and per_sample_path.exists() else "w"

    with per_sample_path.open(mode, encoding="utf-8") as out_handle:
        with input_path.open("r", encoding="utf-8") as in_handle:
            global_index = 0
            local_processed = 0

            for raw_line in in_handle:
                if not raw_line.strip():
                    continue
                if args.limit > 0 and global_index >= args.limit:
                    break

                item = json.loads(raw_line)
                metadata = item.get("metadata", {})
                task_id = str(metadata.get("task_id", global_index))
                if global_index % args.num_shards != args.shard_rank:
                    global_index += 1
                    continue

                if task_id in completed_task_ids:
                    global_index += 1
                    continue

                record = _evaluate_one(
                    item=item,
                    sample_index=global_index,
                    args=args,
                    torch_module=torch_module,
                    tokenizer=tokenizer,
                    model=model,
                    device=device,
                )
                out_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                out_handle.flush()
                processed_records.append(record)
                local_processed += 1

                if local_processed % 10 == 0:
                    print(
                        f"[rank {args.shard_rank}] processed {local_processed} new samples",
                        flush=True,
                    )

                global_index += 1

    all_records: list[dict[str, Any]] = []
    with per_sample_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                all_records.append(json.loads(line))

    summary = _build_summary(all_records, args)
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(
        f"[rank {args.shard_rank}] done: "
        f"new={len(processed_records)} total={len(all_records)} summary={summary_path}",
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate ground-truth perplexity with and without references.",
    )
    parser.add_argument("--input", required=True, help="Input JSONL path")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--model-path", required=True, help="Local model directory")
    parser.add_argument(
        "--prompt-tail-lines",
        type=int,
        default=5,
        help="Use the last N lines from prompt as local completion prefix; default 5",
    )
    parser.add_argument(
        "--reference-shots",
        type=int,
        default=5,
        help="Keep only the first K references from each sample; default 5",
    )
    parser.add_argument(
        "--max-context-tokens",
        type=int,
        default=32768,
        help="Maximum total sequence length; default 32768",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=-1,
        help="Only process the first N samples before sharding; default all",
    )
    parser.add_argument(
        "--num-shards",
        type=int,
        default=1,
        help="Total number of static data shards; default 1",
    )
    parser.add_argument(
        "--shard-rank",
        type=int,
        default=0,
        help="Current shard rank in [0, num-shards); default 0",
    )
    parser.add_argument("--resume", dest="resume", action="store_true", help="Resume from existing shard output")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="Ignore existing shard output")
    parser.set_defaults(resume=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.prompt_tail_lines <= 0:
        raise SystemExit("--prompt-tail-lines must be > 0")
    if args.reference_shots <= 0:
        raise SystemExit("--reference-shots must be > 0")
    if args.max_context_tokens <= 0:
        raise SystemExit("--max-context-tokens must be > 0")
    if args.num_shards <= 0:
        raise SystemExit("--num-shards must be > 0")
    if args.shard_rank < 0 or args.shard_rank >= args.num_shards:
        raise SystemExit("--shard-rank must satisfy 0 <= shard-rank < num-shards")
    if args.limit == 0 or args.limit < -1:
        raise SystemExit("--limit must be -1 or a positive integer")

    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
