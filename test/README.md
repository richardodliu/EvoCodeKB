# 测试说明文档

## 概述

本项目包含全面的测试，覆盖所有核心模块。测试使用 Python 标准库，无需额外依赖。

## 测试模块（13 个）

1. **FingerprintTreeGenerator** - 指纹树生成
2. **KnowledgeRetrieval** - 知识检索算法
3. **Database** - 数据库操作
4. **CodeRecord** - 数据模型
5. **SearchEngine** - 搜索引擎功能
6. **CodeParser** - 代码解析
7. **SyntaxChecker** - 语法验证
8. **ConfigManager** - 配置管理
9. **FileProcessor** - 文件处理
10. **Importer** - 仓库导入
11. **BasicIntegration** - 核心 KnowledgeBase 功能
12. **CLIIntegration** - 命令行接口测试
13. **RetrievalIntegration** - 知识检索流程

## 运行测试

### 运行所有测试

```bash
python test/run_all_tests.py
```

### 运行单个测试模块

```bash
python test/test_database.py
python test/test_basic_integration.py
```

## 测试结构

```
test/
├── README.md                              # 本文件
├── run_all_tests.py                       # 测试运行器
├── test_config_manager.py
├── test_database.py
├── test_file_processor.py
├── test_fingerprint_tree_generator.py
├── test_importer.py
├── test_knowledge_retrieval.py
├── test_models.py
├── test_parser.py
├── test_search_engine.py
├── test_syntax_checker.py
├── test_basic_integration.py
├── test_cli_integration.py
└── test_retrieval_integration.py
```

## 测试特点

- ✓ 零外部依赖（不使用 pytest）
- ✓ 使用标准库的 assert 语句
- ✓ 简单的 main() 函数测试模式
- ✓ 清晰的 ✓/✗ 输出标记
- ✓ 自动清理测试数据（临时文件和数据库）
- ✓ 覆盖正常流程和边界条件
- ✓ 统一的代码风格和结构
- ✓ 中文注释和文档字符串

## 测试统计

- 总测试文件: 13 个
- 测试用例: 60+ 个
- 通过率: 100%
