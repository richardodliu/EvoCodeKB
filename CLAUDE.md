# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EvoCodeKB is a code knowledge base system built on SQLite, packaged as `evokb`. It ingests source code from zip archives, parses semantic units (functions, methods, declaration blocks, etc.) using tree-sitter, generates structure fingerprints (AST-based) and text fingerprints (N-gram-based), and supports keyword search and fingerprint-based similar code retrieval.

Supported languages: C（统一处理 C 和 C++）、Java（配置在 `config/config.json`）。

## Installation

```bash
pip install -e .
```

## Commands

```bash
# Run all tests (15 test modules, 60+ test cases)
python test/run_all_tests.py

# Run a single test module
python test/test_database.py

# Build a knowledge base from zip files (either form works)
evokb update --knowledge_path data/test --knowledge_base test
python main.py update --knowledge_path data/test --knowledge_base test

# Search
evokb search "malloc" --knowledge_base test --type code --lang C

# Retrieve similar code
evokb knowledge_retrieve input.c --knowledge_base test --shots 5

# Stats
evokb stats --knowledge_base test

# Benchmark pipeline
python scripts/demo_database.py
```

## Architecture

**Orchestrator**: `evokb/knowledgebase.py` — `KnowledgeBase` class creates and wires all components together via constructor injection.

**Data flow**:
```
zip archives → FileProcessor → CodeParser (Pygments) → SyntaxChecker (tree-sitter)
→ FingerprintTreeGenerator (tree-sitter) → Database (SQLite) → SearchEngine / KnowledgeRetrieval
```

**Key modules** (all under `evokb/`):
- `config/manager.py` — Language config, file extension mapping, tree-sitter language map (`TREE_SITTER_LANG_MAP`), supported languages list (`SUPPORTED_LANGUAGES`)
- `storage/database.py` — SQLite CRUD, search (SQL LIKE), lightweight fingerprint queries, query-by-ids
- `storage/models.py` — `SemanticRecord` dataclass (the central data model)
- `parsing/parser.py` — Code parsing and semantic unit extraction
- `syntax/checker.py` — tree-sitter syntax validation
- `fingerprint/tree_generator.py` — AST fingerprint generation (MD5-based post-order traversal)
- `retrieval/knowledge_retrieval.py` — Greedy coverage-based top-k retrieval algorithm
- `search/engine.py` — Keyword search wrapper over Database.search()
- `io/file_processor.py` — File reading and extension filtering
- `io/importer.py` — Bulk directory import
- `cli.py` — CLI logic (console_scripts entry point)

**CLI entry points**: `evokb` command (via `pyproject.toml` console_scripts) or `python main.py` (thin wrapper)

## Key Patterns

- **Relative imports** throughout `evokb/` — modules use `from ..config.manager import ...` style
- **Tree-sitter language mapping** is centralized in `evokb/config/manager.py` as `TREE_SITTER_LANG_MAP`. All modules (SyntaxChecker, FingerprintTreeGenerator) import from there.
- **Database uses try/finally** on all methods to prevent connection leaks
- **Database unique constraint**: `UNIQUE(repository, relative_path)` with `INSERT OR REPLACE`
- **Tests use stdlib only** (no pytest) — each test file has a `main()` function returning 0/1, run via `test/run_all_tests.py`

## Design Decisions

- **Text 不区分 code/comment**: `SemanticRecord.text` 存储完整源代码文本（含前导注释），不拆分代码和注释。两种指纹均基于完整 `text` 生成：`structure_fingerprint` 对 `text` 做 tree-sitter AST 遍历，`text_fingerprint` 对 `text` 做 N-gram 哈希。这是设计决策，不是遗漏——测试中构造记录时也必须对完整 `text` 生成指纹，不能只用注释部分。
- **双指纹体系**: `structure_fingerprint`（AST 结构指纹）用于 KnowledgeRetrieval，`text_fingerprint`（N-gram 文本指纹）用于 InformationRetrieval，两条检索路径独立。
- **集合语义指纹（set semantics）**: 指纹列表在检索前转为 `frozenset`，使用集合交并集计算 Jaccard 相似度和覆盖度。不使用 multiset/Counter——重复哈希被去重是有意设计，换取 O(1) 查找和 frozenset 的不可变性/可哈希性。
- **Prefilter 使用 Jaccard 截断**: 当候选数量超过 `max_candidates` 时，先按 Jaccard 相似度取 top-k 再做贪心覆盖。这是性能与精度的权衡——Jaccard prefilter 可能排除低相似度但高互补性的候选，但避免了对全量候选做 O(k×n) 贪心扫描。
- **贪心覆盖 + Jaccard 补齐**: 检索分两阶段——先用贪心覆盖度算法选择互补候选（覆盖查询指纹的不同部分），当覆盖度耗尽（`cur_refer_set` 为空或无正覆盖候选）后提前终止，再按 Jaccard 相似度降序从剩余候选中补齐至 `shots` 数。前者保证结果多样性，后者保证返回数量。
- **Tiebreaker 排序策略**: 当多个候选覆盖度/相似度相同时，按以下优先级依次比较：`KIND_PRIORITY`（`declaration_block` > `function` > `method` > `global` > `type`）→ `line_span` 更短优先 → `qualified_name` 字典序 → `id` 更小优先。设计意图：同等得分时偏好更细粒度、更精确的代码片段——`declaration_block` 作为函数内局部声明块是最小语义单元，短代码片段指纹更集中、噪声更少。这是有意设计，测试 `test_retrieve_prefers_declaration_block_on_tie` 明确验证了此行为。
- **贪心循环时间复杂度**: 贪心覆盖的真实瓶颈在每轮候选评分——`get_coverage_from_sets` 对每个候选做 `frozenset & set` 交集运算。总复杂度 O(k × n × min(|C|, |R|))，其中 k=shots, n=候选数, |C|=候选指纹集大小, |R|=当轮剩余查询指纹集大小（逐轮递减）。典型场景（10,000 候选, |C|=300, shots=10）约 1-2 秒。这是贪心集合覆盖算法的固有复杂度，prefilter 通过限制 n 来控制总开销。
- **返回结果中 `score` 与 `similarity` 的区别**: `score` 是贪心选择时该候选对**当轮剩余查询指纹**的覆盖率（上下文相关，每轮不同），`similarity` 是该候选与**原始查询**的 Jaccard 相似度（上下文无关，全局固定）。两者含义不同是有意设计——`score` 反映贪心互补贡献，`similarity` 反映整体相似程度。同一候选在不同轮次被选中时 `score` 不同但 `similarity` 不变。
- **Jaccard 空集返回 0.0**: `get_jaccard_similarity` 在任一输入为空集时返回 0.0（数学上 Jaccard(∅, ∅) 常定义为 1.0）。这在实际使用中不会触发问题——空指纹的候选在 `_prepare_*_candidates` 阶段已被过滤，不会进入检索流程。
- **AST 指纹遍历全部子节点（含 unnamed token）**: `_traverse_node` 使用 `node.children` 而非 `node.named_children`，遍历包括 `{`、`}`、`(`、`)`、`;`、运算符等语法 token。这是有意设计——运算符（`+`、`-`、`==` 等）是 unnamed token，改用 `named_children` 会导致 `a+b` 与 `a-b` 产生相同的父节点哈希，丧失运算符区分度。高频语法 token（`{`、`;` 等）的叶节点哈希在 `frozenset` 去重后仅占 1 个槽位，不影响 Jaccard 排名。此设计与参考实现一致。
- **父子条目双重入库（type + method）**: 类/结构体作为 `type` 整体入库（含全部方法体），其内部方法也各自作为 `function`/`method` 独立入库。这导致约 2x 存储膨胀，但服务不同检索粒度——类级条目匹配"具有某些方法的类"查询，方法级条目匹配"特定函数实现"查询。贪心算法天然处理了这一冗余：类条目指纹集很大，与小型查询的 Jaccard 相似度低，不会抢占方法条目的排名。
- **宏前缀导致 tree-sitter 节点范围偏大（已知局限）**: tree-sitter 不做宏展开，未知的宏标识符（如 `TEST_END`、`JEMALLOC_ALWAYS_INLINE`）会被解析为 `type_identifier`，导致相邻的宏调用被合并进 `function_definition` 节点。实测 redis 仓库约 1.9% 的记录 text 多出一行不相关的宏前缀。影响极小——指纹仅多 1-2 个 hash，对 Jaccard 排名和覆盖度计算几乎无影响。不修复，接受为 tree-sitter 无预处理器的固有局限。
- **C/C++ 统一为单一语言 "C"**: 所有 C 和 C++ 源文件（`.c`, `.cpp`, `.hpp`, `.cc`, `.cxx`, `.hh`, `.h`）统一记录为语言 `"C"`，均使用 tree-sitter C++ 解析器（`cpp`）解析。设计动机：(1) C++ 解析器是 C 的超集，能正确解析纯 C 代码；(2) 同一 AST 体系下生成的结构指纹可直接跨 C/C++ 比较，检索一致性更好；(3) 消除了检索时需要同时查询 `language IN ('C', 'C++')` 的复杂性。权衡：极少数旧式 C 宏（如 K&R 风格的 `OF((...))` 原型宏）在 C++ 解析器下提取的符号名可能不同，但这类模式在现代代码中极为罕见。配置映射在 `config/config.json` 和 `TREE_SITTER_LANG_MAP`。

## Database Schema

Table `code_knowledge`: id, repository, relative_path, file_extension, language, kind, node_type, symbol_name, qualified_name, parent_qualified_name, start_line, end_line, text, structure_fingerprint, text_fingerprint, created_at. Indexes on repository, file_extension, language, relative_path.

## Data Layout

- `knowledgebase/` — SQLite database files (e.g., `train.db`)
- `data/` — Dataset directories containing zip archives of code repositories
- `benchmark/` — `input.jsonl` (code snippets) and `output.jsonl` (retrieval results)
