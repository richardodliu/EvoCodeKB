#!/usr/bin/env python3
"""Generate single-line completions with and without retrieved references."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import traceback
from pathlib import Path
from typing import Any


PROMPT_MODE_DEFAULT = "c_direct_generation"
PROMPT_BUILDERS = {"strict", "plus_local8", "plus_local16"}
STOP_POLICIES = {"first_newline", "first_nonempty_line"}
DECODE_POLICIES = {"greedy", "beam"}

CONTROL_KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "case", "else"}
TYPE_DECL_RE = re.compile(r"^\s*(typedef\s+)?(struct|enum|union)\b")
CONTROL_LINE_RE = re.compile(r"^\s*(if|for|while|switch|return|sizeof|case|else)\b")


class SampleStatusError(Exception):
    """Expected per-sample validation failure."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _coerce_str(text: Any) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _split_lines(text: Any) -> list[str]:
    return _coerce_str(text).split("\n")


def _tail_lines(text: Any, n: int) -> str:
    lines = _split_lines(text)
    if not lines:
        return ""
    return "\n".join(lines[-n:])


def _encode(tokenizer: Any, text: str) -> list[int]:
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_attention_mask=False,
        return_token_type_ids=False,
        verbose=False,
    )
    return list(encoded["input_ids"])


def _reference_path(ref: dict[str, Any]) -> str:
    repository = ref.get("repository", "")
    relative_path = ref.get("relative_path", "")
    if repository and relative_path:
        return f"{repository}/{relative_path}"
    if relative_path:
        return str(relative_path)
    if repository:
        return str(repository)
    return ""


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
        raise RuntimeError("CUDA is required to run eval_reference_generation.py")
    if torch_module.cuda.is_bf16_supported():
        return torch_module.bfloat16
    return torch_module.float16


def _normalize_line(text: Any) -> str:
    text = _coerce_str(text)
    if "\n" in text:
        return text.split("\n", 1)[0]
    return text


def _first_nonempty_line(text: Any) -> str:
    for line in _coerce_str(text).split("\n"):
        if line.strip():
            return line
    return ""


def _last_nonempty_index(lines: list[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip():
            return index
    return -1


def _tail_raw_context(lines: list[str], raw_end: int, line_count: int) -> str:
    if raw_end < 0:
        return ""
    start = max(0, raw_end - line_count + 1)
    return "\n".join(lines[start : raw_end + 1])


def _merge_text_blocks(first: str, second: str, *, blank_line: bool = False) -> str:
    first = first or ""
    second = second or ""
    if not first:
        return second
    if not second:
        return first
    if second in first:
        return first
    if first in second:
        return second

    first_lines = first.split("\n")
    second_lines = second.split("\n")
    for overlap in range(min(len(first_lines), len(second_lines)), 0, -1):
        if first_lines[-overlap:] == second_lines[:overlap]:
            merged = first_lines + second_lines[overlap:]
            return "\n".join(merged)

    separator = "\n\n" if blank_line else "\n"
    return first.rstrip("\n") + separator + second.lstrip("\n")


def _extract_recent_comment(lines: list[str], anchor_index: int) -> tuple[str, bool]:
    if anchor_index < 0:
        return "", False

    search_start = max(0, anchor_index - 120)
    candidates: list[tuple[int, int]] = []
    index = search_start
    while index <= anchor_index:
        stripped = lines[index].strip()
        if stripped.startswith("//"):
            end = index
            while end + 1 <= anchor_index and lines[end + 1].strip().startswith("//"):
                end += 1
            candidates.append((index, end))
            index = end + 1
            continue
        if "/*" in lines[index]:
            end = index
            while end <= anchor_index:
                if "*/" in lines[end]:
                    candidates.append((index, end))
                    break
                end += 1
            index = end + 1
            continue
        index += 1

    candidates = [candidate for candidate in candidates if anchor_index - candidate[1] <= 24]
    if not candidates:
        return "", False

    start, end = max(candidates, key=lambda item: item[1])
    comment_text = "\n".join(lines[start : end + 1]).strip("\n")
    return comment_text, bool(comment_text)


def _extract_type_declaration(
    lines: list[str], raw_end: int, search_end: int
) -> tuple[str, str, int | None]:
    floor = max(0, search_end - 48)
    for index in range(search_end, floor - 1, -1):
        if TYPE_DECL_RE.match(lines[index].strip()):
            return "\n".join(lines[index : raw_end + 1]), "type_declaration", index
    return "", "", None


def _looks_like_function_anchor(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    if TYPE_DECL_RE.match(stripped):
        return False
    if "(" not in stripped:
        return False
    token = stripped.split("(", 1)[0].strip().split()
    if not token:
        return False
    if token[-1] in CONTROL_KEYWORDS:
        return False
    if CONTROL_LINE_RE.match(stripped):
        return False
    return True


def _extract_function_signature(
    lines: list[str], raw_end: int, search_end: int
) -> tuple[str, str, int | None]:
    floor = max(0, search_end - 48)
    for index in range(search_end, floor - 1, -1):
        if not _looks_like_function_anchor(lines[index]):
            continue

        start = index
        while start > floor:
            previous = lines[start - 1].strip()
            if not previous:
                break
            if previous.startswith("#"):
                break
            if previous.startswith("//") or previous.startswith("/*") or previous.startswith("*"):
                break
            if previous.endswith(";") or previous.endswith("}") or previous.endswith("{"):
                break
            if TYPE_DECL_RE.match(previous):
                break
            if CONTROL_LINE_RE.match(previous):
                break
            start -= 1

        return "\n".join(lines[start : raw_end + 1]), "function_signature", start
    return "", "", None


def _build_prompt_parts(
    prompt_text: str,
    prompt_builder: str,
) -> dict[str, Any]:
    lines = _split_lines(prompt_text)
    if not lines:
        return {
            "prompt_text": "",
            "prompt_extraction_mode_used": f"{prompt_builder}_empty",
            "docstring_found": False,
            "declaration_context_type": "empty",
            "local_context_lines_used": 0,
            "prompt_line_count_observed": 0,
            "prompt_char_count": 0,
        }

    raw_end = len(lines) - 1
    search_end = _last_nonempty_index(lines)
    if search_end < 0:
        return {
            "prompt_text": "\n".join(lines),
            "prompt_extraction_mode_used": f"{prompt_builder}_empty",
            "docstring_found": False,
            "declaration_context_type": "empty",
            "local_context_lines_used": 0,
            "prompt_line_count_observed": len(lines),
            "prompt_char_count": len("\n".join(lines)),
        }

    declaration_text, declaration_context_type, declaration_start = _extract_type_declaration(
        lines, raw_end, search_end
    )
    if not declaration_text:
        declaration_text, declaration_context_type, declaration_start = _extract_function_signature(
            lines, raw_end, search_end
        )

    if not declaration_text:
        declaration_text = _tail_raw_context(lines, raw_end, 8)
        declaration_context_type = "local_scope"
        declaration_start = max(0, raw_end - 7)

    comment_text, docstring_found = _extract_recent_comment(
        lines, declaration_start if declaration_start is not None else search_end
    )

    local_context_lines = 0
    prompt_extraction_mode_used = prompt_builder
    body_text = declaration_text

    if prompt_builder == "plus_local8":
        local_context_lines = 8
    elif prompt_builder == "plus_local16":
        local_context_lines = 16

    if local_context_lines > 0:
        local_context_text = _tail_raw_context(lines, raw_end, local_context_lines)
        body_text = _merge_text_blocks(body_text, local_context_text)

    prompt_text_final = _merge_text_blocks(comment_text, body_text, blank_line=True)
    if not prompt_text_final.strip():
        fallback_lines = max(local_context_lines, 8)
        prompt_text_final = _tail_raw_context(lines, raw_end, fallback_lines)
        prompt_extraction_mode_used = f"{prompt_builder}_fallback_context{fallback_lines}"
        declaration_context_type = "context_fallback"

    return {
        "prompt_text": prompt_text_final,
        "prompt_extraction_mode_used": prompt_extraction_mode_used,
        "docstring_found": docstring_found,
        "declaration_context_type": declaration_context_type,
        "local_context_lines_used": local_context_lines,
        "prompt_line_count_observed": len(prompt_text_final.splitlines()),
        "prompt_char_count": len(prompt_text_final),
    }


def _abstract_reference_body(ref: dict[str, Any]) -> str:
    text = _coerce_str(ref.get("text", "")).strip()
    if not text:
        return ""

    kind = str(ref.get("kind", "")).lower()
    if "function" in kind:
        signature = text.split("{", 1)[0].strip()
        if signature and not signature.endswith(";"):
            signature = signature.rstrip() + ";"
        return signature
    return text


def _reference_segment_text(ref: dict[str, Any], index: int) -> str:
    path = _reference_path(ref)
    kind = ref.get("kind", "")
    header = f"/* Retrieved reference {index}: {path} | {kind} */\n"
    body = _abstract_reference_body(ref)
    return f"{header}{body}\n\n" if body else f"{header}\n"


def _make_stopping_criteria(tokenizer: Any, prompt_length: int, stop_policy: str) -> Any:
    from transformers import StoppingCriteria, StoppingCriteriaList

    class StopOnPolicy(StoppingCriteria):
        def __init__(self, stop_tokenizer: Any, start_length: int, policy: str):
            super().__init__()
            self.stop_tokenizer = stop_tokenizer
            self.start_length = start_length
            self.policy = policy

        def __call__(self, input_ids: Any, scores: Any, **kwargs: Any) -> bool:
            generated_ids = input_ids[0, self.start_length :].tolist()
            if not generated_ids:
                return False
            text = self.stop_tokenizer.decode(
                generated_ids,
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )
            normalized = _coerce_str(text)
            if self.policy == "first_newline":
                return "\n" in normalized
            if self.policy == "first_nonempty_line":
                lines = normalized.split("\n")
                for line in lines[:-1]:
                    if line.strip():
                        return True
                return False
            return False

    return StoppingCriteriaList([StopOnPolicy(tokenizer, prompt_length, stop_policy)])


def _eos_token_ids(tokenizer: Any, model: Any) -> set[int]:
    values: list[int] = []
    for candidate in (
        getattr(model.generation_config, "eos_token_id", None),
        getattr(tokenizer, "eos_token_id", None),
    ):
        if candidate is None:
            continue
        if isinstance(candidate, int):
            values.append(candidate)
        else:
            values.extend(int(value) for value in candidate)
    return {int(value) for value in values}


def _build_no_reference_prefix(
    tokenizer: Any,
    prompt_text: str,
    max_context_tokens: int,
    max_new_tokens: int,
) -> dict[str, Any]:
    prompt_ids_full = _encode(tokenizer, prompt_text)
    available_prefix_budget = max(max_context_tokens - max_new_tokens, 0)
    prompt_ids = prompt_ids_full[-available_prefix_budget:] if available_prefix_budget else []
    return {
        "prefix_ids": prompt_ids,
        "prompt_token_count_used": len(prompt_ids),
        "prompt_token_count_full": len(prompt_ids_full),
        "prompt_was_truncated": len(prompt_ids) < len(prompt_ids_full),
        "prefix_token_count_total": len(prompt_ids),
    }


def _build_with_reference_prefix(
    tokenizer: Any,
    prompt_text: str,
    references: list[dict[str, Any]],
    max_context_tokens: int,
    max_reference_tokens: int,
    max_new_tokens: int,
) -> dict[str, Any]:
    prompt_ids_full = _encode(tokenizer, prompt_text)
    ref_segments: list[dict[str, Any]] = []
    for index, ref in enumerate(references, start=1):
        segment_text = _reference_segment_text(ref, index)
        segment_ids = _encode(tokenizer, segment_text)
        ref_segments.append({"path": _reference_path(ref), "tokens": segment_ids})

    available_prefix_budget = max(max_context_tokens - max_new_tokens, 0)
    reference_budget_tokens_effective = max(min(max_reference_tokens, available_prefix_budget), 0)
    total_reference_tokens = sum(len(segment["tokens"]) for segment in ref_segments)
    reservable_reference_tokens = min(
        max_reference_tokens,
        total_reference_tokens,
        available_prefix_budget,
    )
    prompt_token_budget = max(available_prefix_budget - reservable_reference_tokens, 0)
    prompt_ids = prompt_ids_full[-prompt_token_budget:] if prompt_token_budget else []

    remaining_total_budget = max(available_prefix_budget - len(prompt_ids), 0)
    remaining_reference_budget = min(max_reference_tokens, remaining_total_budget)

    reference_ids: list[int] = []
    used_reference_paths: list[str] = []
    used_indices: set[int] = set()
    reference_partially_truncated = False
    reference_truncated_path: str | None = None
    reference_truncated_tokens_kept = 0
    reference_truncated_tokens_total = 0

    for index, segment in enumerate(ref_segments):
        if remaining_reference_budget <= 0:
            break

        segment_ids = segment["tokens"]
        take_count = min(len(segment_ids), remaining_reference_budget)
        if take_count <= 0:
            continue

        reference_ids.extend(segment_ids[:take_count])
        used_reference_paths.append(segment["path"])
        used_indices.add(index)
        remaining_reference_budget -= take_count

        if take_count < len(segment_ids):
            reference_partially_truncated = True
            reference_truncated_path = segment["path"]
            reference_truncated_tokens_kept = take_count
            reference_truncated_tokens_total = len(segment_ids)
            break

    omitted_reference_paths = [
        segment["path"] for index, segment in enumerate(ref_segments) if index not in used_indices
    ]
    prefix_ids = reference_ids + prompt_ids
    return {
        "prefix_ids": prefix_ids,
        "reference_token_count": len(reference_ids),
        "reference_token_count_total_considered": total_reference_tokens,
        "reference_used_count": len(used_reference_paths),
        "reference_partially_truncated": reference_partially_truncated,
        "reference_applied": bool(reference_ids),
        "used_reference_paths": used_reference_paths,
        "omitted_reference_paths": omitted_reference_paths,
        "reference_omitted_count": len(omitted_reference_paths),
        "reference_truncated_path": reference_truncated_path,
        "reference_truncated_tokens_kept": reference_truncated_tokens_kept,
        "reference_truncated_tokens_total": reference_truncated_tokens_total,
        "reference_budget_tokens_effective": reference_budget_tokens_effective,
        "prompt_token_count_used": len(prompt_ids),
        "prompt_token_count_full": len(prompt_ids_full),
        "prompt_was_truncated": len(prompt_ids) < len(prompt_ids_full),
        "prefix_token_count_total": len(prefix_ids),
    }


def _generate_prediction(
    torch_module: Any,
    tokenizer: Any,
    model: Any,
    device: Any,
    prefix_ids: list[int],
    max_new_tokens: int,
    stop_policy: str,
    decode_policy: str,
    beam_size: int,
) -> dict[str, Any]:
    input_ids = torch_module.tensor([prefix_ids], dtype=torch_module.long, device=device)
    attention_mask = torch_module.ones_like(input_ids)
    eos_token_id = getattr(model.generation_config, "eos_token_id", None)
    pad_token_id = tokenizer.pad_token_id
    if pad_token_id is None:
        if isinstance(eos_token_id, int):
            pad_token_id = eos_token_id
        elif isinstance(eos_token_id, (list, tuple)) and eos_token_id:
            pad_token_id = int(eos_token_id[0])

    stopping_criteria = _make_stopping_criteria(tokenizer, len(prefix_ids), stop_policy)
    num_beams = beam_size if decode_policy == "beam" else 1

    with torch_module.inference_mode():
        output_ids = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            num_beams=num_beams,
            early_stopping=True if num_beams > 1 else False,
            pad_token_id=pad_token_id,
            eos_token_id=eos_token_id,
            stopping_criteria=stopping_criteria,
        )

    generated_ids = output_ids[0, len(prefix_ids) :].tolist()
    raw_text = tokenizer.decode(
        generated_ids,
        skip_special_tokens=False,
        clean_up_tokenization_spaces=False,
    )
    clean_text = tokenizer.decode(
        generated_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )
    if stop_policy == "first_nonempty_line":
        prediction_line = _first_nonempty_line(clean_text)
    else:
        prediction_line = _normalize_line(clean_text)

    normalized_raw = _coerce_str(raw_text)
    eos_ids = _eos_token_ids(tokenizer, model)
    completed_lines = normalized_raw.split("\n")
    stop_reason = "other"
    if not generated_ids:
        stop_reason = "empty"
    elif stop_policy == "first_nonempty_line" and any(
        line.strip() for line in completed_lines[:-1]
    ):
        stop_reason = "first_nonempty_line"
    elif "\n" in normalized_raw:
        stop_reason = "newline"
    elif generated_ids and generated_ids[-1] in eos_ids:
        stop_reason = "eos_token"
    elif len(generated_ids) >= max_new_tokens:
        stop_reason = "max_new_tokens"

    prediction_token_count = len(_encode(tokenizer, prediction_line)) if prediction_line else 0
    return {
        "prediction": prediction_line,
        "prediction_char_count": len(prediction_line),
        "generated_token_count": len(generated_ids),
        "prediction_token_count": prediction_token_count,
        "stop_reason": stop_reason,
        "empty_prediction": prediction_line == "",
    }


def _load_model_stack(model_path: str) -> tuple[Any, Any, Any, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch_dtype = _choose_torch_dtype(torch)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map="auto",
        dtype=torch_dtype,
        local_files_only=True,
    )
    model.eval()
    device = next(model.parameters()).device
    return torch, tokenizer, model, device


def _task_numeric_id(task_id: str, sample_index: int) -> int:
    try:
        return int(task_id)
    except Exception:
        return sample_index


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
        "prompt_mode": PROMPT_MODE_DEFAULT,
        "prompt_builder_requested": args.prompt_builder,
        "prompt_extraction_mode_used": None,
        "docstring_found": False,
        "declaration_context_type": None,
        "local_context_lines_used": 0,
        "stop_policy": args.stop_policy,
        "decode_policy": args.decode_policy,
        "beam_size": args.beam_size if args.decode_policy == "beam" else 1,
        "prompt_was_truncated_no_reference": False,
        "prompt_was_truncated_with_reference": False,
        "reference_shots_requested": args.reference_shots,
        "max_new_tokens_requested": args.max_new_tokens,
        "reference_candidates_total": len(references_all),
        "reference_candidates_considered": len(references_considered),
        "reference_used_count": 0,
        "reference_applied": False,
        "reference_partially_truncated": False,
        "reference_token_count": 0,
        "reference_token_count_total_considered": 0,
        "reference_budget_tokens_effective": 0,
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
        "groundtruth_line_char_count": 0,
        "groundtruth_token_count": 0,
        "prediction_no_reference": None,
        "prediction_with_reference": None,
        "prediction_char_count_no_reference": 0,
        "prediction_char_count_with_reference": 0,
        "generated_token_count_no_reference": 0,
        "generated_token_count_with_reference": 0,
        "prediction_token_count_no_reference": 0,
        "prediction_token_count_with_reference": 0,
        "stop_reason_no_reference": None,
        "stop_reason_with_reference": None,
        "empty_prediction_no_reference": False,
        "empty_prediction_with_reference": False,
        "prompt_context_char_count": 0,
        "prompt_context_line_count": 0,
        "prompt_context_token_count_full": 0,
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
        prompt_parts = _build_prompt_context(item, args.prompt_builder)
        prompt_text = prompt_parts["prompt_text"]
        result["prompt_extraction_mode_used"] = prompt_parts["prompt_extraction_mode_used"]
        result["docstring_found"] = prompt_parts["docstring_found"]
        result["declaration_context_type"] = prompt_parts["declaration_context_type"]
        result["local_context_lines_used"] = prompt_parts["local_context_lines_used"]
        result["prompt_context_char_count"] = prompt_parts["prompt_char_count"]
        result["prompt_context_line_count"] = prompt_parts["prompt_line_count_observed"]
        if prompt_text == "":
            raise SampleStatusError("invalid_prompt_context", "prompt context is empty")

        groundtruth = item.get("groundtruth", "")
        groundtruth = _coerce_str(groundtruth)
        groundtruth_line = _normalize_line(groundtruth)
        result["groundtruth_char_count"] = len(groundtruth)
        result["groundtruth_line_char_count"] = len(groundtruth_line)
        result["groundtruth_token_count"] = len(_encode(tokenizer, groundtruth_line))

        no_ref = _build_no_reference_prefix(
            tokenizer=tokenizer,
            prompt_text=prompt_text,
            max_context_tokens=args.max_context_tokens,
            max_new_tokens=args.max_new_tokens,
        )
        result["prompt_context_token_count_full"] = no_ref["prompt_token_count_full"]
        result["prompt_token_count_used_no_reference"] = no_ref["prompt_token_count_used"]
        result["prefix_token_count_no_reference"] = no_ref["prefix_token_count_total"]
        result["prompt_was_truncated_no_reference"] = no_ref["prompt_was_truncated"]

        no_ref_prediction = _generate_prediction(
            torch_module=torch_module,
            tokenizer=tokenizer,
            model=model,
            device=device,
            prefix_ids=no_ref["prefix_ids"],
            max_new_tokens=args.max_new_tokens,
            stop_policy=args.stop_policy,
            decode_policy=args.decode_policy,
            beam_size=args.beam_size,
        )
        result["prediction_no_reference"] = no_ref_prediction["prediction"]
        result["prediction_char_count_no_reference"] = no_ref_prediction["prediction_char_count"]
        result["generated_token_count_no_reference"] = no_ref_prediction["generated_token_count"]
        result["prediction_token_count_no_reference"] = no_ref_prediction["prediction_token_count"]
        result["stop_reason_no_reference"] = no_ref_prediction["stop_reason"]
        result["empty_prediction_no_reference"] = no_ref_prediction["empty_prediction"]

        if not references:
            result["comparison_status"] = "no_reference_candidates"
            return result

        with_ref = _build_with_reference_prefix(
            tokenizer=tokenizer,
            prompt_text=prompt_text,
            references=references,
            max_context_tokens=args.max_context_tokens,
            max_reference_tokens=args.max_reference_tokens,
            max_new_tokens=args.max_new_tokens,
        )
        result["reference_token_count"] = with_ref["reference_token_count"]
        result["reference_token_count_total_considered"] = with_ref[
            "reference_token_count_total_considered"
        ]
        result["reference_used_count"] = with_ref["reference_used_count"]
        result["reference_applied"] = with_ref["reference_applied"]
        result["reference_partially_truncated"] = with_ref["reference_partially_truncated"]
        result["reference_budget_tokens_effective"] = with_ref[
            "reference_budget_tokens_effective"
        ]
        result["reference_omitted_count"] = with_ref["reference_omitted_count"]
        result["reference_truncated_path"] = with_ref["reference_truncated_path"]
        result["reference_truncated_tokens_kept"] = with_ref["reference_truncated_tokens_kept"]
        result["reference_truncated_tokens_total"] = with_ref[
            "reference_truncated_tokens_total"
        ]
        result["used_reference_paths"] = with_ref["used_reference_paths"]
        result["omitted_reference_paths"] = with_ref["omitted_reference_paths"]
        result["prompt_token_count_used_with_reference"] = with_ref["prompt_token_count_used"]
        result["prefix_token_count_with_reference"] = with_ref["prefix_token_count_total"]
        result["prompt_was_truncated_with_reference"] = with_ref["prompt_was_truncated"]

        if not with_ref["reference_applied"]:
            result["comparison_status"] = "reference_budget_zero"
            return result

        with_ref_prediction = _generate_prediction(
            torch_module=torch_module,
            tokenizer=tokenizer,
            model=model,
            device=device,
            prefix_ids=with_ref["prefix_ids"],
            max_new_tokens=args.max_new_tokens,
            stop_policy=args.stop_policy,
            decode_policy=args.decode_policy,
            beam_size=args.beam_size,
        )
        result["prediction_with_reference"] = with_ref_prediction["prediction"]
        result["prediction_char_count_with_reference"] = with_ref_prediction[
            "prediction_char_count"
        ]
        result["generated_token_count_with_reference"] = with_ref_prediction[
            "generated_token_count"
        ]
        result["prediction_token_count_with_reference"] = with_ref_prediction[
            "prediction_token_count"
        ]
        result["stop_reason_with_reference"] = with_ref_prediction["stop_reason"]
        result["empty_prediction_with_reference"] = with_ref_prediction["empty_prediction"]
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


def _build_summary(records: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    generated = [record for record in records if record.get("prediction_no_reference") is not None]
    with_reference = [
        record for record in records if record.get("prediction_with_reference") is not None
    ]

    def int_mean(field: str, source: list[dict[str, Any]]) -> float | None:
        values = [_safe_int(record.get(field)) for record in source]
        return _mean([float(value) for value in values if value is not None])

    return {
        "input_path": str(Path(args.input).resolve()),
        "output_dir": str(Path(args.output_dir).resolve()),
        "model_path": str(Path(args.model_path).resolve()),
        "prompt_mode": PROMPT_MODE_DEFAULT,
        "prompt_builder": args.prompt_builder,
        "stop_policy": args.stop_policy,
        "decode_policy": args.decode_policy,
        "beam_size": args.beam_size if args.decode_policy == "beam" else 1,
        "reference_shots": args.reference_shots,
        "max_context_tokens": args.max_context_tokens,
        "max_reference_tokens": args.max_reference_tokens,
        "max_new_tokens": args.max_new_tokens,
        "generation_policy": args.decode_policy,
        "stop_boundary": args.stop_policy,
        "num_shards": args.num_shards,
        "shard_rank": args.shard_rank,
        "limit": args.limit,
        "resume": args.resume,
        "split_mod": args.split_mod,
        "split_rem": args.split_rem,
        "samples_total": len(records),
        "samples_generated_no_reference": len(generated),
        "samples_generated_with_reference": len(with_reference),
        "samples_with_reference_candidates": sum(
            1 for record in records if int(record.get("reference_candidates_considered", 0)) > 0
        ),
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
        "empty_prediction_rate_no_reference": _mean(
            [1.0 if record.get("empty_prediction_no_reference") else 0.0 for record in generated]
        ),
        "empty_prediction_rate_with_reference": _mean(
            [1.0 if record.get("empty_prediction_with_reference") else 0.0 for record in with_reference]
        ),
        "docstring_found_rate": _mean(
            [1.0 if record.get("docstring_found") else 0.0 for record in generated]
        ),
        "prompt_extraction_fallback_rate": _mean(
            [
                1.0
                if "fallback" in str(record.get("prompt_extraction_mode_used", ""))
                else 0.0
                for record in generated
            ]
        ),
        "mean_groundtruth_token_count": int_mean("groundtruth_token_count", generated),
        "mean_prompt_token_count_used_no_reference": int_mean(
            "prompt_token_count_used_no_reference", generated
        ),
        "mean_prompt_token_count_used_with_reference": int_mean(
            "prompt_token_count_used_with_reference", with_reference
        ),
        "mean_reference_token_count": int_mean("reference_token_count", with_reference),
        "mean_reference_used_count": int_mean("reference_used_count", with_reference),
        "mean_prediction_token_count_no_reference": int_mean(
            "prediction_token_count_no_reference", generated
        ),
        "mean_prediction_token_count_with_reference": int_mean(
            "prediction_token_count_with_reference", with_reference
        ),
    }


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
        f"prompt_mode={PROMPT_MODE_DEFAULT} builder={args.prompt_builder} "
        f"decode={args.decode_policy} stop={args.stop_policy}",
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

                if args.split_mod > 0:
                    numeric_task_id = _task_numeric_id(task_id, global_index)
                    if numeric_task_id % args.split_mod != args.split_rem:
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
        description="Generate single-line completions with and without references.",
    )
    parser.add_argument("--input", required=True, help="Input JSONL path")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--model-path", required=True, help="Local model directory")
    parser.add_argument(
        "--prompt-builder",
        default="plus_local16",
        choices=sorted(PROMPT_BUILDERS),
        help="Prompt builder; default plus_local16",
    )
    parser.add_argument(
        "--stop-policy",
        default="first_nonempty_line",
        choices=sorted(STOP_POLICIES),
        help="Stopping policy; default first_nonempty_line",
    )
    parser.add_argument(
        "--decode-policy",
        default="greedy",
        choices=sorted(DECODE_POLICIES),
        help="Decode policy; default greedy",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=4,
        help="Beam size when --decode-policy beam; default 4",
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
        "--max-reference-tokens",
        type=int,
        default=8192,
        help="Maximum tokens reserved for references; default 8192",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=128,
        help="Maximum newly generated tokens; default 128",
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
    parser.add_argument(
        "--split-mod",
        type=int,
        default=0,
        help="Optional task-id modulo for dev split selection; 0 disables",
    )
    parser.add_argument(
        "--split-rem",
        type=int,
        default=0,
        help="Required remainder when --split-mod > 0",
    )
    parser.add_argument(
        "--resume",
        dest="resume",
        action="store_true",
        help="Resume from existing shard output",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Ignore existing shard output",
    )
    parser.set_defaults(resume=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.reference_shots <= 0:
        raise SystemExit("--reference-shots must be > 0")
    if args.max_context_tokens <= 0:
        raise SystemExit("--max-context-tokens must be > 0")
    if args.max_reference_tokens <= 0:
        raise SystemExit("--max-reference-tokens must be > 0")
    if args.max_new_tokens <= 0:
        raise SystemExit("--max-new-tokens must be > 0")
    if args.num_shards <= 0:
        raise SystemExit("--num-shards must be > 0")
    if args.shard_rank < 0 or args.shard_rank >= args.num_shards:
        raise SystemExit("--shard-rank must satisfy 0 <= shard-rank < num-shards")
    if args.limit == 0 or args.limit < -1:
        raise SystemExit("--limit must be -1 or a positive integer")
    if args.beam_size <= 1 and args.decode_policy == "beam":
        raise SystemExit("--beam-size must be > 1 when --decode-policy beam")
    if args.split_mod < 0:
        raise SystemExit("--split-mod must be >= 0")
    if args.split_mod > 0 and (args.split_rem < 0 or args.split_rem >= args.split_mod):
        raise SystemExit("--split-rem must satisfy 0 <= split-rem < split-mod")

    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
