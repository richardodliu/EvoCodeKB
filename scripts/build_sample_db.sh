#!/usr/bin/env bash
# 用单个仓库构建知识库，并采样 100 条记录到 JSONL
#
# 用法:
#   bash scripts/build_sample_db.sh [仓库zip路径]
#
# 示例:
#   bash scripts/build_sample_db.sh data/train/redis.zip
#   bash scripts/build_sample_db.sh data/train/curl.zip
#
# 默认使用 data/train/redis.zip

set -euo pipefail

REPO_ZIP="${1:-data/train/redis.zip}"
REPO_NAME="$(basename "$REPO_ZIP" .zip)"
DB_PATH="knowledgebase/${REPO_NAME}.db"
SAMPLE_OUTPUT="scripts/sample_100.jsonl"
SAMPLE_SIZE=100

if [ ! -f "$REPO_ZIP" ]; then
    echo "错误: 找不到 $REPO_ZIP"
    exit 1
fi

# 1. 构建知识库
echo "=== 构建知识库: $REPO_ZIP → $DB_PATH ==="

TEMP_DIR=$(mktemp -d)
ln -sf "$(cd "$(dirname "$REPO_ZIP")" && pwd)/$(basename "$REPO_ZIP")" "$TEMP_DIR/$REPO_NAME.zip"

rm -f "$DB_PATH"
python main.py update --knowledge_path "$TEMP_DIR" --knowledge_base "$REPO_NAME"
rm -rf "$TEMP_DIR"

echo ""

# 2. 采样 100 条记录
echo "=== 采样 ${SAMPLE_SIZE} 条记录 → $SAMPLE_OUTPUT ==="

python3 -c "
import sqlite3, json, random

random.seed(42)
conn = sqlite3.connect('${DB_PATH}')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('SELECT id FROM code_knowledge')
all_ids = [row[0] for row in cursor.fetchall()]
total = len(all_ids)
sample_size = min(${SAMPLE_SIZE}, total)
sampled_ids = sorted(random.sample(all_ids, sample_size))

placeholders = ','.join('?' * len(sampled_ids))
cursor.execute(f'SELECT * FROM code_knowledge WHERE id IN ({placeholders})', sampled_ids)
columns = [desc[0] for desc in cursor.description]

with open('${SAMPLE_OUTPUT}', 'w', encoding='utf-8') as f:
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        for key in ('structure_fingerprint', 'text_fingerprint'):
            if record.get(key):
                record[key] = json.loads(record[key])
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

conn.close()
print(f'总记录数: {total}, 采样: {sample_size} 条')
"

echo "=== 完成: $SAMPLE_OUTPUT ==="
