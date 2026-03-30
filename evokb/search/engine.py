from typing import List, Optional, Dict
from ..storage.database import Database


class SearchEngine:
    """搜索引擎"""

    def __init__(self, database: Database):
        self.database = database

    def search(self,
               query: str,
               language: Optional[str] = None,
               repository: Optional[str] = None,
               kind: Optional[str] = None,
               shots: Optional[int] = None) -> List[Dict]:
        """
        搜索语义条目

        Args:
            query: 搜索关键词
            language: 按语言过滤
            repository: 按仓库过滤
            kind: 按语义类型过滤
            shots: 最多返回条数

        Returns:
            匹配的记录列表
        """
        records = self.database.search(
            keyword=query,
            language=language,
            repository=repository,
            kind=kind,
            limit=shots,
        )

        results = []
        for record in records:
            results.append({
                'id': record.id,
                'repository': record.repository,
                'relative_path': record.relative_path,
                'kind': record.kind,
                'node_type': record.node_type,
                'symbol_name': record.symbol_name,
                'qualified_name': record.qualified_name,
                'parent_qualified_name': record.parent_qualified_name,
                'language': record.language,
                'file_extension': record.file_extension,
                'start_line': record.start_line,
                'end_line': record.end_line,
                'text': record.text,
            })

        return results
