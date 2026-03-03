import json
from typing import List, Dict, Optional
from ..storage.database import Database


class KnowledgeRetrieval:
    """基于覆盖度的知识检索"""

    def __init__(self, database: Database, fp_generator):
        self.database = database
        self.code_fp_generator = fp_generator

    def retrieve(self,
                 input_code: str,
                 language: str,
                 shots: int,
                 repository: Optional[str] = None,
                 limit: int = -1) -> List[Dict]:
        """
        从数据库中检索与输入代码最相关的 top-k 个代码

        Args:
            input_code: 输入代码
            language: 语言类型
            shots: 返回的代码数量
            repository: 可选，限定仓库
            limit: 预过滤候选数量，-1 表示不过滤，正整数表示先按覆盖度取前 N 个再贪心

        Returns:
            List[Dict]: 检索到的代码记录列表
        """
        # 1. 生成输入代码的指纹树
        origin_cur_refer_trees = self.code_fp_generator.generate_fp_tree(input_code, language)
        if not origin_cur_refer_trees:
            print("警告: 无法生成输入代码的指纹树")
            return []

        cur_refer_trees = origin_cur_refer_trees.copy()

        # 2. 从数据库获取候选代码的轻量指纹信息
        db_candidates = self.database.query_fingerprints(language=language, repository=repository)

        if not db_candidates:
            print("警告: 数据库中没有匹配的候选代码")
            return []

        # 3. 解析候选代码的指纹树
        candidate_trees = {}
        valid_candidates = []

        for cand in db_candidates:
            if cand['code_fingerprint']:
                try:
                    fp_tree = json.loads(cand['code_fingerprint'])
                    candidate_trees[cand['id']] = fp_tree
                    valid_candidates.append(cand)
                except Exception as e:
                    print(f"警告: 解析指纹树失败 {cand['relative_path']}: {e}")

        if not valid_candidates:
            print("警告: 没有有效的候选代码（缺少指纹树）")
            return []

        # 3.5 预过滤：按初始覆盖度筛选 top-N 候选
        if limit > 0 and len(valid_candidates) > limit:
            refer_set = set(cur_refer_trees)
            scored = []
            for cand in valid_candidates:
                cand_set = set(candidate_trees[cand['id']])
                score = len(cand_set & refer_set) / len(cur_refer_trees)
                scored.append((cand, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            valid_candidates = [c for c, s in scored[:limit]]

        # 4. 贪心选择 top-k 代码
        top_ids = []
        top_scores = {}
        remaining_candidates = valid_candidates.copy()

        for _ in range(min(shots, len(remaining_candidates))):
            best_score = -1.0
            best_cand = None

            # 遍历所有剩余候选代码
            for cand in remaining_candidates:
                cand_tree = candidate_trees[cand['id']]
                score = self._get_coverage(cand_tree, cur_refer_trees)

                if score > best_score:
                    best_score = score
                    best_cand = cand

            if best_cand is None:
                break

            top_ids.append(best_cand['id'])
            top_scores[best_cand['id']] = best_score

            # 更新剩余树
            best_tree = candidate_trees[best_cand['id']]
            cur_refer_trees = self._update_tree(best_tree, cur_refer_trees)

            # 移除已选代码
            remaining_candidates.remove(best_cand)

        # 5. 按 id 获取完整记录
        full_records = self.database.query_by_ids(top_ids)
        record_map = {r.id: r for r in full_records}

        top_records = []
        for rid in top_ids:
            record = record_map.get(rid)
            if record:
                top_records.append({
                    'id': record.id,
                    'repository': record.repository,
                    'relative_path': record.relative_path,
                    'language': record.language,
                    'text': record.text,
                    'code': record.code,
                    'comment': record.comment,
                    'score': top_scores[rid]
                })

        return top_records

    def _get_coverage(self, cand_tree: List[int], refer_tree: List[int]) -> float:
        """
        计算候选树对参考树的覆盖度

        Args:
            cand_tree: 候选代码的指纹树
            refer_tree: 参考代码的指纹树

        Returns:
            float: 覆盖度 [0, 1]
        """
        if not refer_tree:
            return 0.0

        cand_set = set(cand_tree)
        refer_set = set(refer_tree)

        intersection = cand_set & refer_set
        return len(intersection) / len(refer_set)

    def _update_tree(self, cand_tree: List[int], refer_tree: List[int]) -> List[int]:
        """
        更新参考树，移除已覆盖的节点

        Args:
            cand_tree: 候选代码的指纹树
            refer_tree: 当前参考树

        Returns:
            List[int]: 更新后的参考树
        """
        return list(set(refer_tree) - set(cand_tree))
