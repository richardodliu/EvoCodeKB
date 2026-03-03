# 知识检索功能实现文档

## 概述

基于 AST 指纹树覆盖度的代码检索系统已成功实现。该系统通过预计算代码的 AST 指纹树，使用贪心算法从知识库中检索出与输入代码最相关的 top-k 个代码片段。

## 核心功能

### 1. AST 指纹树生成
- 使用 tree-sitter 解析代码生成 AST
- 后序遍历计算每个节点的 MD5 哈希指纹
- 生成整数哈希值列表作为代码的唯一标识

### 2. 数据库扩展
- 在 `CodeRecord` 模型中添加 `fp_tree` 字段
- 数据库表新增 `fp_tree TEXT` 列存储 JSON 序列化的指纹树
- 在构建知识库时自动预计算并保存指纹树

### 3. 覆盖度检索算法
- 计算输入代码与候选代码的指纹树交集
- 使用贪心策略迭代选择覆盖度最高的代码
- 每次选择后更新剩余未覆盖的树节点

## 文件结构

```
src/
├── fingerprint/
│   ├── __init__.py
│   └── tree_generator.py          # 指纹树生成器
├── retrieval/
│   ├── __init__.py
│   └── knowledge_retrieval.py     # 知识检索实现
├── storage/
│   ├── models.py                  # 添加 fp_tree 字段
│   └── database.py                # 更新表结构
└── knowledgebase.py               # 集成检索功能

scripts/
└── migrate_add_fp_tree.py         # 数据库迁移脚本

test/
└── test_retrieval.py              # 功能测试脚本

main.py                            # 添加 --knowledge_retrieve 命令
test_input.c                       # 测试输入文件
```

## 使用方法

### 1. 构建知识库（自动生成指纹树）

```bash
python main.py --construct_knowledgebase data/test --knowledgebase_name test
```

### 2. 检索相似代码

```bash
python main.py --knowledge_retrieve test_input.c --knowledgebase_name test --shots 5
```

可选参数:
- `--shots N`: 返回 N 个最相似的代码（默认 5）
- `--lang LANG`: 指定语言（默认自动推断）
- `--repo REPO`: 限定仓库范围

### 3. 迁移现有数据库

```bash
python scripts/migrate_add_fp_tree.py knowledgebase/test.db
```

## 测试结果

运行 `python test/test_retrieval.py` 验证:

```
✓ 指纹树生成: 通过
✓ 数据库存储: 通过
✓ 知识检索: 通过
```

测试覆盖:
- 指纹树生成和序列化
- 数据库存储和查询
- 覆盖度计算和贪心选择

## 性能优势

| 方面 | 原始实现 | 新实现 |
|------|---------|--------|
| 指纹树计算 | 每次检索时计算 | 构建时预计算 |
| 存储位置 | 内存 | 数据库持久化 |
| 检索速度 | O(n*m) | O(n) |
| 可扩展性 | 受内存限制 | 支持大规模数据 |

## API 接口

### KnowledgeBase.retrieve_similar_codes()

```python
def retrieve_similar_codes(
    self,
    input_code: str,
    language: str,
    shots: int = 5,
    repository: Optional[str] = None
) -> List[Dict]
```

返回格式:
```python
[
    {
        'id': 1,
        'repository': 'redis',
        'relative_path': 'src/server.c',
        'language': 'C',
        'text': '...',
        'code': '...',
        'score': 0.8523  # 覆盖度 [0, 1]
    },
    ...
]
```

## 注意事项

1. **语言支持**: 目前支持 C, C++, Python, Java
2. **数据库兼容**: 新建数据库自动包含 fp_tree 字段，旧数据库需要迁移
3. **性能**: 大规模数据库建议添加索引优化查询速度
4. **精度**: 覆盖度为 1.0 表示完全匹配，0.0 表示无交集

## 后续优化方向

1. 批量并行计算指纹树
2. 添加数据库索引优化查询
3. 支持更多编程语言
4. 混合检索（覆盖度 + 语义相似度）
5. 增量索引支持实时更新
