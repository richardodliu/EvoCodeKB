# AGENTS.md

This file provides guidance to Code Agents (codex) when working with code in this repository.

## Project Overview

EvoCodeKB is a code knowledge base system built on SQLite, packaged as `evokb`. It ingests source code from zip archives, separates code from comments using Pygments, validates syntax and generates AST fingerprints using tree-sitter, and supports keyword search and fingerprint-based similar code retrieval.

Supported languages: C, C++, Python, Java (configured in `evokb/config.json`).

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
- `storage/models.py` — `CodeRecord` dataclass (the central data model)
- `parsing/parser.py` — Pygments-based code/comment separation
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

## Database Schema

Table `code_knowledge`: id, repository, relative_path, text, code, comment, file_extension, language, code_fingerprint, created_at. Indexes on repository, file_extension, language, relative_path.

## Data Layout

- `knowledgebase/` — SQLite database files (e.g., `train.db`)
- `data/` — Dataset directories containing zip archives of code repositories
- `benchmark/` — `input.jsonl` (code snippets) and `output.jsonl` (retrieval results)
