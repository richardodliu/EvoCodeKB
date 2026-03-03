from typing import List, Optional, Dict
from ..storage.database import Database


class SearchEngine:
    """搜索引擎"""

    def __init__(self, database: Database):
        self.database = database

    def search(self,
               query: str,
               search_type: str = 'all',
               language: Optional[str] = None,
               repository: Optional[str] = None) -> List[Dict]:
        """
        搜索代码库

        Args:
            query: 搜索关键词
            search_type: 'all' | 'code' | 'comment' | 'text'
            language: 按语言过滤
            repository: 按仓库过滤

        Returns:
            匹配的记录列表
        """
        records = self.database.search(
            keyword=query,
            search_type=search_type,
            language=language,
            repository=repository,
        )

        results = []
        for record in records:
            results.append({
                'id': record.id,
                'repository': record.repository,
                'relative_path': record.relative_path,
                'language': record.language,
                'file_extension': record.file_extension,
                'text': record.text,
                'code': record.code,
                'comment': record.comment
            })

        return results
