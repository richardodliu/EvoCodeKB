# EvoCodeKB - 可演进的代码知识库

一个基于 SQLite 的代码知识库系统，支持代码和注释的分离存储与检索。

## 特性

- 使用 Pygments 进行精确的词法分析，正确提取代码和注释
- 支持从 zip 压缩包批量导入多个仓库
- 支持多仓库管理，记录仓库名和相对路径
- 基于 SQLite 的轻量级存储
- 灵活的检索接口（按语言、仓库、类型过滤）
- 命令行工具支持

## 数据组织

```
data/
├── test/              # 数据集名称
│   ├── redis.zip     # 代码仓库压缩包
│   ├── repo2.zip
│   └── repo3.zip
└── train/            # 另一个数据集
    ├── repoA.zip
    └── repoB.zip
```

每个 zip 文件代表一个代码仓库，zip 文件名（去掉 .zip）作为仓库名。

## 安装依赖

```bash
pip install pygments
```

## 快速开始

### 1. 构建知识库

从数据集目录构建知识库（自动处理所有 zip 文件）：

```bash
python main.py --construct_knowledgebase data/test --knowledgebase_name test
```

输出示例：
```
找到 1 个仓库压缩包

处理仓库: redis
  找到 720 个文件
  ✓ redis 导入完成 (成功: 720, 失败: 0)

==================================================
全部导入完成！
总文件数: 720
成功: 720
失败: 0
==================================================

数据库统计:
  总记录数: 720
  按语言: {'C': 720}
  按仓库: {'redis': 720}
```

### 2. 查看统计信息

```bash
python main.py --stats test
```

输出示例：
```
总文件数: 720

按语言:
  C: 720

按仓库:
  redis: 720
```

### 3. 搜索代码

```bash
# 在代码中搜索
python main.py --search "malloc" --knowledgebase_name test --type code --limit 5

# 在注释中搜索
python main.py --search "Redis" --knowledgebase_name test --type comment --limit 10

# 全文搜索
python main.py --search "list" --knowledgebase_name test --lang C

# 按仓库过滤
python main.py --search "malloc" --knowledgebase_name test --repo redis
```

### 4. 重置数据库

```bash
python main.py --reset test
```

## 命令行参数

### 构建知识库
```bash
python main.py --construct_knowledgebase <dataset_dir> --knowledgebase_name <kb_name>
```
从数据集目录构建知识库，自动处理目录下所有 .zip 文件。

参数：
- `--construct_knowledgebase` - 数据集目录路径（如 data/test）
- `--knowledgebase_name` - 知识库名称（如 test），保存到 knowledgebase/test.db

### 查看统计
```bash
python main.py --stats <kb_name>
```
显示数据库统计信息（总文件数、按语言、按仓库）。

### 搜索
```bash
python main.py --search <query> --knowledgebase_name <kb_name> [options]
```

选项：
- `--type all|code|comment|text` - 搜索范围（默认 all）
- `--lang C` - 按语言过滤
- `--repo <repo_name>` - 按仓库过滤
- `--limit N` - 最多显示 N 条结果（默认 10）

### 重置数据库
```bash
python main.py --reset <kb_name>
```
删除并重新初始化数据库。

## 编程接口

```python
from src.code_kb import CodeKnowledgeBase

# 创建知识库实例
kb = CodeKnowledgeBase('knowledgebase/test.db')

# 从内存中的内容处理文件
result = kb.process_file_from_content(
    content=file_content,
    file_path='src/adlist.c',
    repository='redis',
    relative_path='src/adlist.c'
)

# 保存到数据库
kb.update_database_from_dict(result)

# 搜索
results = kb.search_database(
    query='malloc',
    search_type='code',
    language='C',
    repository='redis'
)

# 获取统计信息
stats = kb.get_stats()
print(stats)
```

## 配置

编辑 `config.json` 添加新的语言支持：

```json
{
    "languages": [
        {
            "name": "C",
            "extensions": [".c", ".h"]
        }
    ]
}
```

## 数据库结构

表名：`code_knowledge`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| repository | TEXT | 仓库名 |
| relative_path | TEXT | 文件相对路径 |
| text | TEXT | 完整文本 |
| code | TEXT | 去除注释的代码 |
| comment | TEXT | 提取的注释 |
| file_extension | TEXT | 文件后缀 |
| language | TEXT | 语言类型 |
| created_at | TIMESTAMP | 创建时间 |

**唯一性约束**：`UNIQUE(repository, relative_path)` - 同一仓库中的相对路径唯一

## 测试

运行基础功能测试：
```bash
python test/test_basic.py
```

## 项目结构

```
EvoCodeKB/
├── main.py              # 命令行入口
├── config.json          # 语言配置
├── knowledgebase/       # 数据库目录
│   └── test.db          # 知识库数据库
├── src/
│   ├── __init__.py
│   └── code_kb.py       # 核心模块
├── data/
│   └── test/            # 数据集目录
│       └── redis.zip    # 代码仓库压缩包
├── test/
│   ├── test_basic.py    # 基础功能测试
│   └── test_cli.py      # 命令行测试
└── docs/
    └── README.md
```

## 技术栈

- Python 3.7+
- SQLite3
- Pygments（词法分析）
- zipfile（处理压缩包）

## License

MIT
