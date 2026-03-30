#!/usr/bin/env python3
"""Run paper-mode generation config sweeps and rank by no-reference quality."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GRID = [
    {"prompt_builder": "strict", "decode_policy": "greedy", "beam_size": 1, "max_new_tokens": 128},
    {"prompt_builder": "strict", "decode_policy": "beam", "beam_size": 4, "max_new_tokens": 128},
    {"prompt_builder": "plus_local8", "decode_policy": "greedy", "beam_size": 1, "max_new_tokens": 128},
    {"prompt_builder": "plus_local8", "decode_policy": "beam", "beam_size": 4, "max_new_tokens": 128},
    {"prompt_builder": "plus_local16", "decode_policy": "greedy", "beam_size": 1, "max_new_tokens": 128},
    {"prompt_builder": "plus_local16", "decode_policy": "beam", "beam_size": 4, "max_new_tokens": 128},
]


def _read_summary(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _run_launcher(args: argparse.Namespace, config: dict[str, Any]) -> tuple[Path, str]:
    launcher = [
        "bash",
        str(Path(args.repo_root) / "scripts" / "run_reference_generation_gpu.sh"),
        "--foreground",
        "--input",
        args.input,
        "--output-jsonl",
        args.output_jsonl,
        "--model-path",
        args.model_path,
        "--num-gpus",
        str(args.num_gpus),
        "--reference-shots",
        str(args.reference_shots),
        "--prompt-builder",
        config["prompt_builder"],
        "--stop-policy",
        "first_nonempty_line",
        "--decode-policy",
        config["decode_policy"],
        "--beam-size",
        str(config["beam_size"]),
        "--max-new-tokens",
        str(config["max_new_tokens"]),
        "--split-mod",
        str(args.split_mod),
        "--split-rem",
        str(args.split_rem),
    ]
    if args.limit > 0:
        launcher.extend(["--limit", str(args.limit)])

    completed = subprocess.run(
        launcher,
        cwd=args.repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    run_meta_path: Path | None = None
    for line in completed.stdout.splitlines():
        if line.startswith("Run metadata: "):
            run_meta_path = Path(line.split(": ", 1)[1].strip())
    if run_meta_path is None:
        raise RuntimeError(f"Failed to locate run metadata path in launcher output:\n{completed.stdout}")
    meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
    return Path(meta["run_dir"]), completed.stdout


def _score_key(row: dict[str, Any]) -> tuple[float, float, float, int, int]:
    return (
        float(row.get("mean_em_no_reference") or 0.0),
        float(row.get("mean_es_no_reference") or 0.0),
        -float(row.get("empty_prediction_rate_no_reference") or 0.0),
        0 if row.get("prompt_builder") == "strict" else 1 if row.get("prompt_builder") == "plus_local8" else 2,
        0 if row.get("decode_policy") == "greedy" else 1,
    )


def _write_outputs(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "baseline_calibration_summary.json"
    csv_path = output_dir / "baseline_calibration_table.csv"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "best": rows[0] if rows else None,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rank",
                "run_dir",
                "prompt_builder",
                "decode_policy",
                "beam_size",
                "max_new_tokens",
                "mean_em_no_reference",
                "mean_es_no_reference",
                "empty_prediction_rate_no_reference",
                "gap_to_target_em",
                "gap_to_target_es",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate generation configs.")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--input", required=True, help="Input JSONL path")
    parser.add_argument("--output-jsonl", required=True, help="Output JSONL path used by runs")
    parser.add_argument("--model-path", required=True, help="Model path")
    parser.add_argument("--num-gpus", type=int, default=8, help="GPU count for launcher")
    parser.add_argument("--reference-shots", type=int, default=5, help="Reference shots")
    parser.add_argument("--split-mod", type=int, default=10, help="Dev split modulo")
    parser.add_argument("--split-rem", type=int, default=0, help="Dev split remainder")
    parser.add_argument("--limit", type=int, default=-1, help="Optional limit for smoke calibration")
    parser.add_argument(
        "--output-dir",
        default="benchmark/runs/reference_gen_qwen25coder7b/calibration_latest",
        help="Directory for calibration reports",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    args.repo_root = str(repo_root)
    rows: list[dict[str, Any]] = []

    for config in DEFAULT_GRID:
        run_dir, _ = _run_launcher(args, config)
        summary = _read_summary(run_dir)
        rows.append(
            {
                "rank": 0,
                "run_dir": str(run_dir),
                "prompt_builder": config["prompt_builder"],
                "decode_policy": config["decode_policy"],
                "beam_size": summary.get("beam_size"),
                "max_new_tokens": config["max_new_tokens"],
                "mean_em_no_reference": summary.get("mean_em_no_reference"),
                "mean_es_no_reference": summary.get("mean_es_no_reference"),
                "empty_prediction_rate_no_reference": summary.get("empty_prediction_rate_no_reference"),
                "gap_to_target_em": summary.get("gap_to_target_em"),
                "gap_to_target_es": summary.get("gap_to_target_es"),
            }
        )

    rows.sort(key=_score_key, reverse=True)

    if rows and not any(row.get("mean_em_no_reference") is not None for row in rows):
        raise RuntimeError(
            "Calibration split produced zero valid samples. "
            "Increase --limit or disable split selection with --split-mod 0."
        )

    rerun_candidates = rows[:2]
    if rows and (rows[0].get("empty_prediction_rate_no_reference") or 0.0) > 0.15:
        extra_rows: list[dict[str, Any]] = []
        for candidate in rerun_candidates:
            config = {
                "prompt_builder": candidate["prompt_builder"],
                "decode_policy": candidate["decode_policy"],
                "beam_size": candidate["beam_size"],
                "max_new_tokens": 192,
            }
            run_dir, _ = _run_launcher(args, config)
            summary = _read_summary(run_dir)
            extra_rows.append(
                {
                    "rank": 0,
                    "run_dir": str(run_dir),
                    "prompt_builder": config["prompt_builder"],
                    "decode_policy": config["decode_policy"],
                    "beam_size": summary.get("beam_size"),
                    "max_new_tokens": config["max_new_tokens"],
                    "mean_em_no_reference": summary.get("mean_em_no_reference"),
                    "mean_es_no_reference": summary.get("mean_es_no_reference"),
                    "empty_prediction_rate_no_reference": summary.get("empty_prediction_rate_no_reference"),
                    "gap_to_target_em": summary.get("gap_to_target_em"),
                    "gap_to_target_es": summary.get("gap_to_target_es"),
                }
            )
        rows.extend(extra_rows)
        rows.sort(key=_score_key, reverse=True)

    for index, row in enumerate(rows, start=1):
        row["rank"] = index

    _write_outputs(Path(args.output_dir), rows)
    print(json.dumps({"best": rows[0] if rows else None, "rows": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
