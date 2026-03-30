import json
import warnings
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List, Optional, Sequence, Tuple

from ..fingerprint.tree_generator import FingerprintTreeGenerator
from ..storage.database import Database
from ._common import (
    KIND_PRIORITY,
    _kind_priority,
    _line_span,
    containment_prefilter_sort_key,
    get_containment,
    get_coverage_from_sets,
    is_better_candidate,
    resolve_candidate_languages,
    resolve_max_candidates,
    resolve_worker_count,
    results_from_selected_candidates,
    update_refer_set,
)


_KNOWLEDGE_BATCH_CANDIDATES = []
_KNOWLEDGE_BATCH_FP_GENERATOR = None


def _prepare_knowledge_candidates(
    rows: Sequence[Dict], include_text: bool, verbose: bool
) -> List[Dict]:
    prepared = []
    for row in rows:
        raw_fingerprint = row.get("structure_fingerprint")
        if not raw_fingerprint:
            continue
        try:
            fp_tree = json.loads(raw_fingerprint)
        except Exception as exc:
            if verbose:
                print(f"警告: 解析指纹树失败 {row['relative_path']}: {exc}")
            continue

        candidate = {
            "id": row["id"],
            "repository": row["repository"],
            "relative_path": row["relative_path"],
            "language": row["language"],
            "kind": row["kind"],
            "node_type": row["node_type"],
            "symbol_name": row["symbol_name"],
            "qualified_name": row["qualified_name"],
            "parent_qualified_name": row["parent_qualified_name"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "fingerprint_set": frozenset(fp_tree),
        }
        if include_text:
            candidate["text"] = row["text"]
        prepared.append(candidate)
    return prepared


def _select_knowledge_candidates(
    input_code: str,
    language: str,
    shots: int,
    limit: int,
    max_candidates: int,
    candidates: Sequence[Dict],
    fp_generator: FingerprintTreeGenerator,
) -> Optional[Tuple[List[Tuple[Dict, float]], frozenset]]:
    """返回 (selected_candidates, query_fingerprint_set) 或 None。"""
    origin_refer_tree = fp_generator.generate_fp_tree(input_code, language)
    if not origin_refer_tree:
        return None

    cur_refer_set = set(origin_refer_tree)
    query_structure_fingerprint_set = frozenset(origin_refer_tree)
    selected: List[Tuple[Dict, float]] = []

    remaining_candidates = list(candidates)
    prefilter_count = resolve_max_candidates(limit, max_candidates)
    if prefilter_count > 0 and len(remaining_candidates) > prefilter_count:
        scored = []
        for candidate in remaining_candidates:
            cont = get_containment(
                candidate["fingerprint_set"],
                query_structure_fingerprint_set,
            )
            scored.append((candidate, cont))
        scored.sort(key=lambda item: containment_prefilter_sort_key(item[0], item[1]))
        remaining_candidates = [candidate for candidate, _ in scored[:prefilter_count]]

    selected_ids = set()
    for _ in range(min(shots, len(remaining_candidates))):
        if not cur_refer_set:
            break

        best_score = 0.0
        best_candidate = None

        for candidate in remaining_candidates:
            if candidate["id"] in selected_ids:
                continue
            score = get_coverage_from_sets(candidate["fingerprint_set"], cur_refer_set)
            if score > best_score or (
                score == best_score and is_better_candidate(candidate, best_candidate)
            ):
                best_score = score
                best_candidate = candidate

        if best_candidate is None or best_score <= 0.0:
            break

        selected_ids.add(best_candidate["id"])
        selected.append((best_candidate, best_score))
        cur_refer_set = update_refer_set(best_candidate["fingerprint_set"], cur_refer_set)

    # 覆盖度用完后，按 containment 降序补齐剩余 shots
    remaining_shots = shots - len(selected)
    if remaining_shots > 0:
        backfill_candidates = [c for c in remaining_candidates if c["id"] not in selected_ids]
        containment_ranked = sorted(
            backfill_candidates,
            key=lambda c: containment_prefilter_sort_key(
                c,
                get_containment(c["fingerprint_set"], query_structure_fingerprint_set),
            ),
        )
        for candidate in containment_ranked[:remaining_shots]:
            selected.append((candidate, 0.0))

    return selected, query_structure_fingerprint_set


def _init_knowledge_worker(candidates: Sequence[Dict]):
    global _KNOWLEDGE_BATCH_CANDIDATES, _KNOWLEDGE_BATCH_FP_GENERATOR
    _KNOWLEDGE_BATCH_CANDIDATES = list(candidates)
    _KNOWLEDGE_BATCH_FP_GENERATOR = FingerprintTreeGenerator()


def _run_knowledge_worker(task: Tuple[str, str, int, int, int]) -> List[Dict]:
    input_code, language, shots, limit, max_candidates = task
    try:
        result = _select_knowledge_candidates(
            input_code,
            language,
            shots,
            limit,
            max_candidates,
            _KNOWLEDGE_BATCH_CANDIDATES,
            _KNOWLEDGE_BATCH_FP_GENERATOR,
        )
        if result is None:
            return []
        selected_candidates, query_fp_set = result
        return results_from_selected_candidates(selected_candidates, query_fp_set)
    except Exception as exc:
        warnings.warn(f"Knowledge retrieval worker 异常: {type(exc).__name__}: {exc}")
        return []


class KnowledgeRetrieval:
    """基于覆盖度的知识检索"""

    KIND_PRIORITY = KIND_PRIORITY

    def __init__(self, database: Database, fp_generator):
        self.database = database
        self.structure_fp_generator = fp_generator
        self._candidate_cache = {}

    def retrieve(
        self,
        input_code: str,
        language: str,
        shots: int,
        repository: Optional[str] = None,
        limit: int = -1,
        max_candidates: int = -1,
    ) -> List[Dict]:
        prepared_candidates = self._load_prepared_candidates(
            language=language,
            repository=repository,
            include_text=True,
            verbose=True,
        )
        if not prepared_candidates:
            print("警告: 数据库中没有匹配的候选条目")
            return []

        result = _select_knowledge_candidates(
            input_code,
            language,
            shots,
            limit,
            max_candidates,
            prepared_candidates,
            self.structure_fp_generator,
        )
        if result is None:
            print("警告: 无法生成输入代码的指纹树")
            return []

        selected_candidates, query_fp_set = result
        return results_from_selected_candidates(selected_candidates, query_fp_set)

    def retrieve_many(
        self,
        input_codes: List[str],
        language: str,
        shots: int,
        repository: Optional[str] = None,
        limit: int = -1,
        max_candidates: int = -1,
        max_workers: Optional[int] = None,
    ) -> List[List[Dict]]:
        if not input_codes:
            return []

        prepared_candidates = self._load_prepared_candidates(
            language=language,
            repository=repository,
            include_text=True,
            verbose=False,
        )
        if not prepared_candidates:
            return [[] for _ in input_codes]

        worker_count = resolve_worker_count(len(input_codes), max_workers)
        if worker_count <= 1:
            results = []
            for input_code in input_codes:
                result = _select_knowledge_candidates(
                    input_code,
                    language,
                    shots,
                    limit,
                    max_candidates,
                    prepared_candidates,
                    self.structure_fp_generator,
                )
                if result is None:
                    results.append([])
                else:
                    selected, query_fp_set = result
                    results.append(
                        results_from_selected_candidates(selected, query_fp_set)
                    )
            return results

        tasks = [
            (input_code, language, shots, limit, max_candidates)
            for input_code in input_codes
        ]
        with ProcessPoolExecutor(
            max_workers=worker_count,
            initializer=_init_knowledge_worker,
            initargs=(prepared_candidates,),
        ) as executor:
            return list(executor.map(_run_knowledge_worker, tasks))

    def _load_prepared_candidates(
        self,
        language: str,
        repository: Optional[str],
        include_text: bool,
        verbose: bool,
    ) -> List[Dict]:
        cache_key = (resolve_candidate_languages(language), repository, include_text)
        cached = self._candidate_cache.get(cache_key)
        if cached is not None:
            return cached
        rows = self.database.query_retrieval_candidates(
            language=cache_key[0],
            repository=repository,
            include_text=include_text,
        )
        prepared_candidates = _prepare_knowledge_candidates(
            rows, include_text=include_text, verbose=verbose
        )
        if verbose and rows and not prepared_candidates:
            print("警告: 没有有效的候选条目（缺少结构指纹）")
        self._candidate_cache[cache_key] = prepared_candidates
        return prepared_candidates

    def _get_coverage(self, cand_tree: List[int], refer_tree: List[int]) -> float:
        return get_coverage_from_sets(set(cand_tree), set(refer_tree))

    def _is_better_candidate(self, candidate: Dict, incumbent: Optional[Dict]) -> bool:
        return is_better_candidate(candidate, incumbent)

    def _line_span(self, candidate: Dict) -> int:
        return _line_span(candidate)

    def _update_tree(self, cand_tree: List[int], refer_tree: List[int]) -> List[int]:
        return sorted(update_refer_set(set(cand_tree), set(refer_tree)))
