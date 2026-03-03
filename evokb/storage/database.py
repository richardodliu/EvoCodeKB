import sqlite3
from datetime import datetime
from typing import List, Optional, Dict
from .models import CodeRecord


class Database:
    """数据库操作类"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS code_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    text TEXT NOT NULL,
                    code TEXT NOT NULL,
                    comment TEXT,
                    file_extension TEXT,
                    language TEXT,
                    code_fingerprint TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    comment_fingerprint TEXT,
                    UNIQUE(repository, relative_path)
                )
            ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_repository ON code_knowledge(repository)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_extension ON code_knowledge(file_extension)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_language ON code_knowledge(language)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_relative_path ON code_knowledge(relative_path)')

            # 迁移：为已存在的数据库添加 comment_fingerprint 列
            cursor.execute("PRAGMA table_info(code_knowledge)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'comment_fingerprint' not in columns:
                cursor.execute("ALTER TABLE code_knowledge ADD COLUMN comment_fingerprint TEXT")

            conn.commit()
        finally:
            conn.close()

    def insert(self, record: CodeRecord):
        """插入或更新记录"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO code_knowledge
                (repository, relative_path, text, code, comment, file_extension, language, code_fingerprint, created_at, comment_fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.repository,
                record.relative_path,
                record.text,
                record.code,
                record.comment,
                record.file_extension,
                record.language,
                record.code_fingerprint,
                datetime.now(),
                record.comment_fingerprint,
            ))
            conn.commit()
        finally:
            conn.close()

    def query(self,
              language: Optional[str] = None,
              repository: Optional[str] = None) -> List[CodeRecord]:
        """查询记录"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            query = 'SELECT * FROM code_knowledge WHERE 1=1'
            params = []

            if language:
                query += ' AND language = ?'
                params.append(language)
            if repository:
                query += ' AND repository = ?'
                params.append(repository)

            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        records = []
        for row in rows:
            records.append(CodeRecord(
                id=row[0],
                repository=row[1],
                relative_path=row[2],
                text=row[3],
                code=row[4],
                comment=row[5],
                file_extension=row[6],
                language=row[7],
                code_fingerprint=row[8],
                created_at=row[9],
                comment_fingerprint=row[10]
            ))
        return records

    def get_stats(self) -> Dict:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # 总文件数
            cursor.execute('SELECT COUNT(*) FROM code_knowledge')
            total_files = cursor.fetchone()[0]

            # 按语言统计
            cursor.execute('SELECT language, COUNT(*) FROM code_knowledge GROUP BY language')
            by_language = dict(cursor.fetchall())

            # 按仓库统计
            cursor.execute('SELECT repository, COUNT(*) FROM code_knowledge GROUP BY repository')
            by_repository = dict(cursor.fetchall())
        finally:
            conn.close()

        return {
            'total_files': total_files,
            'by_language': by_language,
            'by_repository': by_repository
        }

    def search(self,
               keyword: str,
               search_type: str = 'all',
               language: Optional[str] = None,
               repository: Optional[str] = None) -> List[CodeRecord]:
        """使用 SQL LIKE 搜索记录"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            like_param = f'%{keyword}%'

            if search_type == 'code':
                field_condition = 'code LIKE ?'
            elif search_type == 'comment':
                field_condition = 'comment LIKE ?'
            elif search_type == 'text':
                field_condition = 'text LIKE ?'
            else:  # 'all'
                field_condition = '(code LIKE ? OR comment LIKE ? OR text LIKE ?)'

            query = f'SELECT * FROM code_knowledge WHERE {field_condition}'
            params = [like_param] if 'OR' not in field_condition else [like_param, like_param, like_param]

            if language:
                query += ' AND language = ?'
                params.append(language)
            if repository:
                query += ' AND repository = ?'
                params.append(repository)

            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        records = []
        for row in rows:
            records.append(CodeRecord(
                id=row[0],
                repository=row[1],
                relative_path=row[2],
                text=row[3],
                code=row[4],
                comment=row[5],
                file_extension=row[6],
                language=row[7],
                code_fingerprint=row[8],
                created_at=row[9],
                comment_fingerprint=row[10]
            ))
        return records

    def query_fingerprints(self,
                           language: Optional[str] = None,
                           repository: Optional[str] = None) -> List[Dict]:
        """轻量查询，只返回 id 和 code_fingerprint 等轻量字段"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            query = 'SELECT id, repository, relative_path, language, code_fingerprint, comment_fingerprint FROM code_knowledge WHERE 1=1'
            params = []

            if language:
                query += ' AND language = ?'
                params.append(language)
            if repository:
                query += ' AND repository = ?'
                params.append(repository)

            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [
            {
                'id': row[0],
                'repository': row[1],
                'relative_path': row[2],
                'language': row[3],
                'code_fingerprint': row[4],
                'comment_fingerprint': row[5],
            }
            for row in rows
        ]

    def query_by_ids(self, ids: List[int]) -> List[CodeRecord]:
        """按 id 列表查询完整记录"""
        if not ids:
            return []

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in ids)
            cursor.execute(
                f'SELECT * FROM code_knowledge WHERE id IN ({placeholders})',
                ids
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        records = []
        for row in rows:
            records.append(CodeRecord(
                id=row[0],
                repository=row[1],
                relative_path=row[2],
                text=row[3],
                code=row[4],
                comment=row[5],
                file_extension=row[6],
                language=row[7],
                code_fingerprint=row[8],
                created_at=row[9],
                comment_fingerprint=row[10]
            ))
        return records
