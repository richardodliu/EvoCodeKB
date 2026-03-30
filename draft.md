# EvoCodeKB 全面代码审查与修复计划

## 审查范围

对整个 EvoCodeKB 仓库进行了全面审查，包括 35 个有未提交变更的文件，覆盖存储层、解析层、指纹生成、检索算法、搜索引擎、CLI、配置管理和全部 15 个测试模块。测试运行结果：安装 `tree_sitter_language_pack` 后 15/15 全部通过。

---

## 三、Medium — 建议修复的问题

### 3.4 检索模块大量重复代码 — `knowledge_retrieval.py` vs `information_retrieval.py`

**问题**: `_prepare_*_candidates`、`_select_*_candidates`、`_hydrate_selected_candidates` 三组函数在两个模块中几乎完全相同。

**建议**: 抽取到 `_common.py`。

### 3.12 `has_non_global_ancestor` 重复遍历 parent 链 — `classifier.py:104-115`

**问题**: 每个 global 候选节点都做完整 parent 链遍历，O(depth × candidates)。

**建议**: 利用 scopes 信息避免重复遍历。

### 3.15 `_visit_wrapped_definition` 只处理第一个语义子节点 — `parser.py:155-170`

**问题**: 若 wrapper 节点（如 `template_declaration`）含多个语义子节点，只有第一个被处理。

**建议**: 遍历处理所有语义子节点。

---

## 四、Low — 可以改进但非紧急的问题

### 4.4 `query_by_ids` 不保证返回顺序 — `database.py:369-385`

**问题**: SQL `IN` 查询不保证顺序，调用方用 `record_map` 处理所以无影响，但 API 行为不明确。

**建议**: 在文档中说明返回顺序不保证，或添加排序保证。

### 4.5 `KnowledgeBase` 缺少 `close()` / 上下文管理 — `knowledgebase.py`

**问题**: 无 `__enter__/__exit__`，未来改为长连接时需要。

**建议**: 添加上下文管理器支持。

### 4.7 缺少数据库 `delete` 操作 — `database.py`

**问题**: 知识库只能增加不能删除。移除仓库需重建整个数据库。

**建议**: 添加 `delete_by_repository(repo_name)` 方法。

### 4.8 `__init__.py` 导入链导致环境依赖 — `evokb/__init__.py`

**问题**: 模块级 `from .knowledgebase import ...` 触发整个依赖链（含 `tree_sitter_language_pack`）。缺少该包时即使只 import `Database` 也会失败。

**建议**: 延迟导入或拆分 `__init__.py` 导出。

### 4.9 `get_parser` 代码在两个类中重复 — `tree_generator.py:15-24` vs `parser.py:25-34`

**问题**: `FingerprintTreeGenerator.get_parser()` 与 `SemanticParser.get_parser()` 完全相同。

**建议**: 抽取共享的 `get_parser()` 工具函数。

---

## 六、总结

| 严重程度 | 数量 | 关键发现 |
|---------|------|---------|
| Low | 5 | 返回顺序（4.4）、上下文管理（4.5）、delete（4.7）、导入链（4.8）、get_parser 重复（4.9） |

> **注**: 已修复项（1.1-1.5、2.1-2.2、2.5-2.6、2.8-2.11、3.2-3.3、3.5-3.6、3.8-3.11、3.13-3.14、4.6、P1-P3、P5、P9、P11-P12、R1-R4、R7、R11、I3、I5、I10、5.2-5.4 全部 15 项测试问题）已从本文档中删除。设计决策（P8、P10、R2、R3、R8-R10、R13-R14、I4 及全部 N-gram 局限性问题）已记录到 CLAUDE.md。不修复项（3.4 检索模块重复代码、3.12 parent 链遍历、3.15 wrapper 子节点、R5 多进程内存）经评估为无需修复。深度审查 P 系列条目已全部处理完毕。

剩余 5 项 Low 级别改进（4.4-4.9），按需处理

---

## 九、知识检索（Retrieval）深度审查

对 `evokb/retrieval/` 下 3 个模块（knowledge_retrieval.py、information_retrieval.py、_common.py）及上游指纹生成（`fingerprint/tree_generator.py`、`fingerprint/text_generator.py`）进行逐行算法审查。审查范围覆盖贪心覆盖度算法、预过滤策略、指纹表示、多进程并行、结果构建等全链路。

---

### R5 — High: ProcessPoolExecutor 序列化大候选集 — 内存翻倍 + 启动延迟爆炸 — `knowledge_retrieval.py:279-284`, `information_retrieval.py:225-230`

**问题**: 多进程并行通过 `initargs` 将全部候选传递给每个 worker：

```python
with ProcessPoolExecutor(
    max_workers=worker_count,
    initializer=_init_knowledge_worker,
    initargs=(prepared_candidates,),     # 全部候选 pickle 到每个 worker
) as executor:
    return list(executor.map(_run_knowledge_worker, tasks))
```

`initargs` 通过 `pickle` 序列化并通过管道发送到每个 worker 进程。每个 worker 反序列化并存储在全局变量中。

**内存模型分析**:

对于 10,000 个候选，每个含 ~300 元素的 frozenset：
- 每个 128 位 int 在 Python 中占 ~36 bytes（PyLong 对象头 + 值）
- 每个 frozenset 的元素: 300 × 36 = ~10.8 KB
- frozenset 对象本身（哈希表）: ~300 × 8 = ~2.4 KB 指针数组
- 每个 candidate dict: ~12 个键值对 + frozenset ≈ ~14 KB
- 10,000 候选: ~140 MB 内存

序列化到每个 worker:
- pickle 序列化: ~140 MB × worker_count 次序列化 + IPC 传输
- worker 反序列化: ~140 MB × worker_count 次反序列化
- 峰值内存: 主进程 140 MB + 每 worker 140 MB

4 个 worker: 主进程 + 4 worker = **~700 MB** 仅用于候选数据

**启动延迟**: pickle 序列化 140 MB dict 列表需要数秒。4 个 worker 意味着 4 次序列化 + 4 次 IPC + 4 次反序列化。对于只有几个查询的 `retrieve_many`，并行化的启动开销可能超过计算收益。

**更严重的是**: 如果 `include_text=True`（retrieve_many 路径），每个候选还包含完整的代码文本。1000 行代码 ≈ 20-40 KB 文本。10,000 候选 × 30 KB = ~300 MB。加上指纹数据，总计 ~440 MB × worker_count。

**修复方案**:

方案 A — 共享内存（推荐）:
```python
import multiprocessing as mp

# 将候选数据放入共享内存
shared_candidates = mp.Manager().list(prepared_candidates)
# 或使用 multiprocessing.shared_memory (Python 3.8+)
```

方案 B — 预先分片:
```python
# 将查询分配到 worker，但不复制候选（每个 worker 独立从数据库加载）
def _run_knowledge_worker(task):
    # 每个 worker 自己加载候选（从数据库）
    db = Database(db_path)
    candidates = load_candidates(db, ...)
```

方案 C — 使用线程池 + 控制 GIL 释放:
由于主要计算是 set 交集（C 实现，释放 GIL），ThreadPoolExecutor 可能更高效。

方案 D — 简单阈值:
```python
# 查询数量少时避免并行化
if len(input_codes) < worker_count * 3:
    worker_count = 1
```

---

### 检索审查总结

| 编号 | 严重度 | 问题 | 文件:行 |
|------|--------|------|---------|
| R5 | High | ProcessPoolExecutor 序列化大候选集，内存翻倍 | knowledge_retrieval.py:279-284 |

**核心结论**:

1. **最严重的工程问题**: R5（多进程内存爆炸）。大规模使用时内存效率堪忧。

2. **修复优先级**: R5（性能优化）→ 其余

3. **贪心覆盖度算法本身是正确的**: 标准 (1-1/e) 近似保证在无 prefilter 截断时成立。集合语义（frozenset 去重）和 Jaccard prefilter 策略是有意的性能与精度权衡（详见 CLAUDE.md 设计决策）。

---

## 十、信息检索（InformationRetrieval）深度审查

对 `evokb/retrieval/information_retrieval.py`、`evokb/fingerprint/text_generator.py`（即 `TextFingerprintGenerator`）以及端到端调用链进行逐行审查，并用**实验验证**确认关键缺陷。本章聚焦于信息检索**特有**的问题（与知识检索共有的问题不再重复）。

---

（信息检索部分的问题均为 N-gram 技术的固有局限或已修复/已确认为设计决策，已全部清理。）
