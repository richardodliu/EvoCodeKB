import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Union

from .models import SemanticRecord


TABLE_NAME = "code_knowledge"
EXPECTED_COLUMNS = [
    "id",
    "repository",
    "relative_path",
    "file_extension",
    "language",
    "kind",
    "node_type",
    "symbol_name",
    "qualified_name",
    "parent_qualified_name",
    "start_line",
    "end_line",
    "text",
    "structure_fingerprint",
    "text_fingerprint",
    "created_at",
]


class Database:
    """语义级数据库操作类。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (TABLE_NAME,),
            )
            table_exists = cursor.fetchone() is not None

            if table_exists:
                cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
                columns = [row[1] for row in cursor.fetchall()]
                expected_set = set(EXPECTED_COLUMNS)
                actual_set = set(columns)
                missing = expected_set - actual_set
                if missing:
                    raise RuntimeError(
                        f"数据库缺少必要列: {missing}，请删除旧数据库并重新构建知识库。"
                    )
            else:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        repository TEXT NOT NULL,
                        relative_path TEXT NOT NULL,
                        file_extension TEXT,
                        language TEXT,
                        kind TEXT NOT NULL,
                        node_type TEXT NOT NULL,
                        symbol_name TEXT NOT NULL,
                        qualified_name TEXT NOT NULL,
                        parent_qualified_name TEXT,
                        start_line INTEGER NOT NULL,
                        end_line INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        structure_fingerprint TEXT,
                        text_fingerprint TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(repository, relative_path, kind, qualified_name, start_line, end_line)
                    )
                    """
                )

            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_repository ON {TABLE_NAME}(repository)"
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_relative_path ON {TABLE_NAME}(relative_path)"
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_language ON {TABLE_NAME}(language)"
            )
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_kind ON {TABLE_NAME}(kind)")
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_qualified_name ON {TABLE_NAME}(qualified_name)"
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_start_line ON {TABLE_NAME}(start_line)"
            )

            conn.commit()
        finally:
            conn.close()

    def insert(self, record: SemanticRecord):
        """插入或更新单条语义记录。"""
        self.insert_many([record])

    def insert_many(self, records: Sequence[SemanticRecord]):
        """批量插入或更新记录。"""
        if not records:
            return

        batch_time = datetime.now()
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                cursor = conn.cursor()
                cursor.executemany(
                    f"""
                    INSERT INTO {TABLE_NAME}
                    (
                        repository, relative_path, file_extension, language, kind, node_type,
                        symbol_name, qualified_name, parent_qualified_name, start_line, end_line,
                        text, structure_fingerprint, text_fingerprint, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repository, relative_path, kind, qualified_name, start_line, end_line)
                    DO UPDATE SET
                        file_extension=excluded.file_extension,
                        language=excluded.language,
                        node_type=excluded.node_type,
                        symbol_name=excluded.symbol_name,
                        parent_qualified_name=excluded.parent_qualified_name,
                        text=excluded.text,
                        structure_fingerprint=excluded.structure_fingerprint,
                        text_fingerprint=excluded.text_fingerprint,
                        created_at=excluded.created_at
                    """,
                    [
                        (
                            record.repository,
                            record.relative_path,
                            record.file_extension,
                            record.language,
                            record.kind,
                            record.node_type,
                            record.symbol_name,
                            record.qualified_name,
                            record.parent_qualified_name,
                            record.start_line,
                            record.end_line,
                            record.text,
                            record.structure_fingerprint,
                            record.text_fingerprint,
                            record.created_at or batch_time,
                        )
                        for record in records
                    ],
                )
        finally:
            conn.close()

    def query(
        self,
        language: Optional[str] = None,
        repository: Optional[str] = None,
        kind: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[SemanticRecord]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            query = f"SELECT * FROM {TABLE_NAME} WHERE 1=1"
            params: list = []

            if language is not None:
                query += " AND language = ?"
                params.append(language)
            if repository is not None:
                query += " AND repository = ?"
                params.append(repository)
            if kind is not None:
                query += " AND kind = ?"
                params.append(kind)

            query += " ORDER BY repository, relative_path, start_line, end_line, qualified_name"
            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        return self._rows_to_records(rows)

    def get_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
            total_entries = cursor.fetchone()[0]

            cursor.execute(f"SELECT language, COUNT(*) FROM {TABLE_NAME} GROUP BY language")
            by_language = dict(cursor.fetchall())

            cursor.execute(f"SELECT repository, COUNT(*) FROM {TABLE_NAME} GROUP BY repository")
            by_repository = dict(cursor.fetchall())

            cursor.execute(f"SELECT kind, COUNT(*) FROM {TABLE_NAME} GROUP BY kind")
            by_kind = dict(cursor.fetchall())
        finally:
            conn.close()

        return {
            "total_entries": total_entries,
            "by_language": by_language,
            "by_repository": by_repository,
            "by_kind": by_kind,
        }

    def search(
        self,
        keyword: str,
        language: Optional[str] = None,
        repository: Optional[str] = None,
        kind: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[SemanticRecord]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = f"SELECT * FROM {TABLE_NAME} WHERE text LIKE ? ESCAPE '\\'"
            params: list = [f"%{escaped}%"]

            if language is not None:
                query += " AND language = ?"
                params.append(language)
            if repository is not None:
                query += " AND repository = ?"
                params.append(repository)
            if kind is not None:
                query += " AND kind = ?"
                params.append(kind)

            query += " ORDER BY repository, relative_path, start_line, end_line, qualified_name"
            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        return self._rows_to_records(rows)

    def query_fingerprints(
        self,
        language: Optional[str] = None,
        repository: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            query = (
                f"SELECT id, repository, relative_path, language, kind, node_type, symbol_name, "
                "qualified_name, parent_qualified_name, start_line, end_line, "
                f"structure_fingerprint, text_fingerprint FROM {TABLE_NAME} WHERE 1=1"
            )
            params = []

            if language is not None:
                query += " AND language = ?"
                params.append(language)
            if repository is not None:
                query += " AND repository = ?"
                params.append(repository)
            if kind is not None:
                query += " AND kind = ?"
                params.append(kind)

            query += " ORDER BY repository, relative_path, start_line, end_line, qualified_name"
            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [
            {
                "id": row[0],
                "repository": row[1],
                "relative_path": row[2],
                "language": row[3],
                "kind": row[4],
                "node_type": row[5],
                "symbol_name": row[6],
                "qualified_name": row[7],
                "parent_qualified_name": row[8],
                "start_line": row[9],
                "end_line": row[10],
                "structure_fingerprint": row[11],
                "text_fingerprint": row[12],
            }
            for row in rows
        ]

    def query_retrieval_candidates(
        self,
        language: Optional[Union[str, Sequence[str]]] = None,
        repository: Optional[str] = None,
        kind: Optional[str] = None,
        include_text: bool = False,
    ) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            select_columns = [
                "id",
                "repository",
                "relative_path",
                "language",
                "kind",
                "node_type",
                "symbol_name",
                "qualified_name",
                "parent_qualified_name",
                "start_line",
                "end_line",
            ]
            if include_text:
                select_columns.append("text")
            select_columns.extend(["structure_fingerprint", "text_fingerprint"])

            query = (
                f"SELECT {', '.join(select_columns)} FROM {TABLE_NAME} WHERE 1=1"
            )
            params = []

            if language is not None:
                if isinstance(language, str):
                    query += " AND language = ?"
                    params.append(language)
                else:
                    language_values = list(language)
                    if language_values:
                        placeholders = ",".join("?" for _ in language_values)
                        query += f" AND language IN ({placeholders})"
                        params.extend(language_values)
            if repository is not None:
                query += " AND repository = ?"
                params.append(repository)
            if kind is not None:
                query += " AND kind = ?"
                params.append(kind)

            query += " ORDER BY repository, relative_path, start_line, end_line, qualified_name"
            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        candidates = []
        for row in rows:
            row_index = 0
            candidate = {
                "id": row[row_index],
                "repository": row[row_index + 1],
                "relative_path": row[row_index + 2],
                "language": row[row_index + 3],
                "kind": row[row_index + 4],
                "node_type": row[row_index + 5],
                "symbol_name": row[row_index + 6],
                "qualified_name": row[row_index + 7],
                "parent_qualified_name": row[row_index + 8],
                "start_line": row[row_index + 9],
                "end_line": row[row_index + 10],
            }
            row_index += 11
            if include_text:
                candidate["text"] = row[row_index]
                row_index += 1
            candidate["structure_fingerprint"] = row[row_index]
            candidate["text_fingerprint"] = row[row_index + 1]
            candidates.append(candidate)

        return candidates

    def query_by_ids(self, ids: List[int]) -> List[SemanticRecord]:
        if not ids:
            return []

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in ids)
            cursor.execute(
                f"SELECT * FROM {TABLE_NAME} WHERE id IN ({placeholders})",
                ids,
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        return self._rows_to_records(rows)

    def _rows_to_records(self, rows: Sequence[Sequence]) -> List[SemanticRecord]:
        return [
            SemanticRecord(
                id=row[0],
                repository=row[1],
                relative_path=row[2],
                file_extension=row[3],
                language=row[4],
                kind=row[5],
                node_type=row[6],
                symbol_name=row[7],
                qualified_name=row[8],
                parent_qualified_name=row[9],
                start_line=row[10],
                end_line=row[11],
                text=row[12],
                structure_fingerprint=row[13],
                text_fingerprint=row[14],
                created_at=row[15],
            )
            for row in rows
        ]
