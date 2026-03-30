# EvoCodeKB

一个基于 SQLite 的可演进代码知识库，当前按“语义单元”存储源码，不再按整文件入库。

## 当前模型

- 存储粒度：`function`、`method`、`type`、`global`、`declaration_block`
- `declaration_block` 仅用于 `function` / `method` 体内的连续局部声明块
- 每条记录保留原始源码切片 `text`
- 每条记录带 `start_line` / `end_line`
- 不再区分 `code` 和 `comment`，两种指纹均基于完整 `text`（含前导注释）生成
- 同一个 `text` 同时支持两种检索：
  - `knowledge_retrieve`：基于 AST 结构指纹（tree-sitter 遍历 `text`）
  - `information_retrieve`：基于全文本 N-gram 指纹（对 `text` 提取词级 N-gram）
- AST 结构指纹遍历全部子节点（含运算符等 unnamed token），保留运算符区分度
- 指纹使用集合语义（`frozenset`），Jaccard/覆盖度基于集合交并集计算
- 候选量大时先按 Jaccard 相似度 prefilter 取 top-k，再做贪心覆盖选择
- 贪心覆盖度耗尽后按 Jaccard 相似度降序补齐至 `shots` 数（前者保证多样性，后者保证返回数量）
- 同分候选按 tiebreaker 排序：`KIND_PRIORITY`（细粒度优先）→ 行数更短优先 → 限定名字典序 → id 更小优先
- 检索结果同时返回 `score`（当轮覆盖率，上下文相关）和 `similarity`（全局 Jaccard，上下文无关）

父子条目允许同时存在。例如类/结构体会保留完整定义（`type`），类内方法也会单独存储（`method`），服务不同粒度的检索需求。存储膨胀约 2x，但贪心算法天然按指纹集大小调节排名。

## 支持语言

- **C**（统一处理 C 和 C++，所有 `.c`/`.cpp`/`.hpp`/`.cc`/`.cxx`/`.hh`/`.h` 文件均记录为语言 `"C"`，使用 tree-sitter C++ 解析器）
- **Java**

> **设计说明**: C 和 C++ 统一为单一语言标识 `"C"`。C++ 解析器是 C 的超集，能正确解析纯 C 代码，同时保证 C/C++ 代码在同一 AST 体系下生成结构指纹，检索时无需跨语言查询。

> **已知局限**: tree-sitter 不做宏展开，未知的宏标识符（如 `TEST_END`、`JEMALLOC_ALWAYS_INLINE`）可能被解析为类型名，导致约 1.9% 的记录 text 多出一行不相关的宏前缀。对指纹和检索排名影响极小。

## 安装

```bash
pip install -e .
```

依赖：

- `pygments`
- `tree-sitter-language-pack`

## 数据组织

```text
data/
├── test/
│   ├── redis.zip
│   └── repo2.zip
└── train/
    ├── repoA.zip
    └── repoB.zip
```

每个 `zip` 文件代表一个仓库，文件名去掉 `.zip` 后作为仓库名。

## 命令行

### 1. 构建知识库

```bash
python main.py update --knowledge_path data/test --knowledge_base test
```

导入时会读取配置里支持的全部扩展名，并把每个源码文件切分成语义条目后入库。

### 2. 查看统计

```bash
python main.py stats --knowledge_base test
```

输出包含：

- 总条目数
- 按语言统计
- 按仓库统计
- 按语义类型统计

### 3. 搜索语义条目

```bash
python main.py search "malloc" --knowledge_base test --shots 5
python main.py search "linked list" --knowledge_base test --kind type
python main.py search "printf" --knowledge_base test --repo redis --kind function
```

搜索只针对 `text` 字段，不再区分 `code/comment/text`。

### 4. 结构检索

```bash
python main.py knowledge_retrieve input.c --knowledge_base test --shots 5 --lang C
```

用于检索和输入代码结构最相似的语义条目。

### 5. 信息检索

```bash
python main.py information_retrieve input.txt --knowledge_base test --shots 5
```

用于检索和输入自然语言/文本描述最相关的语义条目。

## Python 接口

```python
from evokb.knowledgebase import KnowledgeBase

kb = KnowledgeBase("knowledgebase/test.db")

records = kb.process_file_from_content(
    content=file_content,
    file_path="src/adlist.c",
    repository="redis",
    relative_path="src/adlist.c",
)

kb.update_database_from_records(records)

results = kb.search_database(
    query="malloc",
    language="C",
    repository="redis",
    kind="function",
)

similar = kb.knowledge_retrieve(input_code, "C", shots=5)
related = kb.information_retrieve("allocate memory for buffer", shots=5)
```

## 数据库结构

表名：`code_knowledge`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| repository | TEXT | 仓库名 |
| relative_path | TEXT | 文件相对路径 |
| file_extension | TEXT | 文件后缀 |
| language | TEXT | 语言 |
| kind | TEXT | `declaration_block/global/function/method/type` |
| node_type | TEXT | tree-sitter 原始节点类型 |
| symbol_name | TEXT | 当前条目名 |
| qualified_name | TEXT | 层级限定名 |
| parent_qualified_name | TEXT | 父级限定名 |
| start_line | INTEGER | 起始行，1-based |
| end_line | INTEGER | 结束行，1-based，闭区间 |
| text | TEXT | 原始源码切片 |
| structure_fingerprint | TEXT | AST 指纹 JSON |
| text_fingerprint | TEXT | 文本指纹 JSON |
| created_at | TIMESTAMP | 创建时间 |

唯一性约束：

```text
UNIQUE(repository, relative_path, kind, qualified_name, start_line, end_line)
```

## 兼容性说明

- 旧版“文件级 + `code/comment` 分离”的数据库与当前 schema 不兼容
- 如果已有旧库，直接删除 `.db` 文件后重建

## 测试

```bash
python test/run_all_tests.py
```
