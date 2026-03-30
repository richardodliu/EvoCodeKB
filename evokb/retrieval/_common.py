"""knowledge_retrieval 和 information_retrieval 的公共工具函数。"""

import os
from typing import Dict, List, Optional, Sequence, Tuple


KIND_PRIORITY = {
    "declaration_block": 0,
    "function": 1,
    "method": 2,
    "global": 3,
    "type": 4,
}


def _line_span(candidate: Dict) -> int:
    start_line = candidate.get("start_line") or 0
    end_line = candidate.get("end_line") or start_line
    return max(0, end_line - start_line)


def _kind_priority(candidate: Dict) -> int:
    return KIND_PRIORITY.get(candidate.get("kind"), 99)


def is_better_candidate(candidate: Dict, incumbent: Optional[Dict]) -> bool:
    if incumbent is None:
        return True

    candidate_rank = _kind_priority(candidate)
    incumbent_rank = _kind_priority(incumbent)
    if candidate_rank != incumbent_rank:
        return candidate_rank < incumbent_rank

    candidate_span = _line_span(candidate)
    incumbent_span = _line_span(incumbent)
    if candidate_span != incumbent_span:
        return candidate_span < incumbent_span

    candidate_name = candidate.get("qualified_name", "")
    incumbent_name = incumbent.get("qualified_name", "")
    if candidate_name != incumbent_name:
        return candidate_name < incumbent_name

    return candidate.get("id", 0) < incumbent.get("id", 0)


def get_coverage_from_sets(candidate_fp_set, refer_set) -> float:
    if not refer_set:
        return 0.0
    return len(candidate_fp_set & refer_set) / len(refer_set)


def update_refer_set(candidate_fp_set, refer_set):
    return refer_set - candidate_fp_set


def get_containment(candidate_fp_set, query_fp_set) -> float:
    """查询集的包含度：候选覆盖了查询的多少比例。"""
    if not query_fp_set:
        return 0.0
    return len(candidate_fp_set & query_fp_set) / len(query_fp_set)


def containment_prefilter_sort_key(candidate: Dict, containment: float):
    """按 containment 降序排序，tiebreaker 不变。"""
    return (
        -containment,
        _kind_priority(candidate),
        _line_span(candidate),
        candidate.get("qualified_name", ""),
        candidate.get("id", 0),
    )


def resolve_worker_count(total_inputs: int, max_workers: Optional[int]) -> int:
    if total_inputs <= 1:
        return 1
    if max_workers is not None:
        return max(1, min(total_inputs, max_workers))
    return max(1, min(total_inputs, os.cpu_count() or 1))


def resolve_candidate_languages(language: Optional[str]):
    if not language:
        return None
    return (language,)


def resolve_max_candidates(limit: int, max_candidates: int) -> int:
    if max_candidates > 0:
        return max_candidates
    return limit


def result_from_candidate(candidate: Dict, score: float, containment: float) -> Dict:
    return {
        "id": candidate["id"],
        "repository": candidate["repository"],
        "relative_path": candidate["relative_path"],
        "language": candidate["language"],
        "kind": candidate["kind"],
        "node_type": candidate["node_type"],
        "symbol_name": candidate["symbol_name"],
        "qualified_name": candidate["qualified_name"],
        "parent_qualified_name": candidate["parent_qualified_name"],
        "start_line": candidate["start_line"],
        "end_line": candidate["end_line"],
        "text": candidate.get("text", ""),
        "score": score,
        "containment": containment,
    }


def results_from_selected_candidates(
    selected_candidates: Optional[Sequence[Tuple[Dict, float]]],
    query_fingerprint_set,
) -> List[Dict]:
    if not selected_candidates:
        return []
    return [
        result_from_candidate(
            candidate,
            score,
            get_containment(candidate["fingerprint_set"], query_fingerprint_set),
        )
        for candidate, score in selected_candidates
    ]
