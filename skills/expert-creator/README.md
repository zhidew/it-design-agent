# Expert Creator - 专家创建器

## 概述

Expert Creator 是一个系统级专家，负责智能生成新的设计专家。它具备完整的 ReAct 能力，能够：
- 分析领域需求并设计专家能力
- 从系统工具注册中心推荐合适的工具
- 生成完整的专家配置（Profile、Skill、模板、脚本）
- 管理系统内置工具

## 核心能力

### 1. ReAct 工作流

Expert Creator 使用 Think-Act-Observe 循环来完成专家创建：

```
Phase 1: Requirement Analysis
  Think: 分析用户意图
  Act: 读取工具注册表
  Observe: 可用工具列表

Phase 2: Tool Recommendation
  Think: 分析工具需求
  Act: 参考现有专家模式
  Observe: 相似专家的工具配置

Phase 3: Expert Design
  Think: 设计专家配置
  Act: 生成专家 Profile
  Observe: 配置文件已创建

Phase 4: Skill Guide Creation
  Think: 设计 ReAct 工作流
  Act: 生成 SKILL.md
  Observe: 技能指南已创建

Phase 5: Template Design
  Think: 设计输出模板
  Act: 创建 Jinja2 模板
  Observe: 模板已创建

Phase 6: Script Implementation (Optional)
  Think: 是否需要自定义脚本？
  Act: 创建脚本文件
  Observe: 脚本已创建
```

### 2. 工具注册中心管理

系统内置工具注册在 `assets/TOOL_REGISTRY.yaml` 中：

```yaml
tools:
  - name: query_database
    category: database
    description_zh: "查询数据库元数据或执行只读SQL"
    input_schema:
      db_id:
        type: string
        required: true
      query_type:
        type: string
        required: true
    use_cases:
      - "分析数据库结构"
    recommended_for:
      - "data-design"
      - "api-design"
```

### 3. 智能工具推荐

根据专家领域关键词自动推荐工具：

```python
from skills.expert_creator.scripts.tool_manager import ToolManager

manager = ToolManager(base_dir)
tools = manager.recommend_tools_for_domain(["api", "database"])
# 返回: ["query_database", "query_knowledge_base", "write_file", "read_file_chunk"]
```

## 文件结构

```
skills/expert-creator/
├── SKILL.md                      # 技能指南 + LLM 指令文件
├── assets/
│   ├── TOOL_REGISTRY.yaml        # 系统工具注册中心
│   └── templates/
│       ├── expert_profile_template.yaml.j2  # Expert Profile 模板
│       └── skill_template.md.j2              # SKILL.md 模板
├── scripts/
│   ├── generate_expert.py        # 专家生成脚本
│   └── tool_manager.py           # 工具管理脚本（命令行工具）
└── references/
```

## UI 功能

### 工具清单 Tab

Expert Architect 在专家中心界面中有一个专用的"工具清单"tab，显示：
- 系统内置工具列表及其分类
- 每个工具的中文/英文描述
- 输入输出 Schema
- 使用场景
- 工具实现代码（Python）

**位置**: 专家列表 → Expert Architect → 工具清单 Tab

### 创建新专家

```python
from skills.expert_creator.scripts.generate_expert import ExpertGenerator
from pathlib import Path

generator = ExpertGenerator(Path("/path/to/project"))
expert = generator.create_expert(
    expert_id="security-audit",
    name="安全审计专家",
    description="分析系统安全状况并生成审计报告"
)

print(f"Created expert: {expert['id']}")
print(f"Recommended tools: {expert['tools_recommended']}")
```

### 管理工具注册中心

```python
from skills.expert_creator.scripts.tool_manager import ToolManager

manager = ToolManager(Path("/path/to/project"))

# 添加新工具
manager.add_tool({
    "name": "new_tool",
    "category": "analysis",
    "description_zh": "新工具描述",
    "description_en": "New tool description",
    "input_schema": {...},
    "use_cases": [...]
})

# 获取推荐工具
tools = manager.recommend_tools_for_domain(["api", "database"])

# 查询特定专家的工具
tools = manager.get_tools_for_expert("api-design")
```

### 命令行使用

```bash
# 列出所有工具
python skills/expert-creator/scripts/tool_manager.py list

# 推荐工具
python skills/expert-creator/scripts/tool_manager.py recommend api database security
```

## 内置工具分类

| 分类 | 工具 | 用途 |
|------|------|------|
| 文件操作 | write_file, patch_file, read_file_chunk, list_files, grep_search | 文件读写、搜索 |
| 数据库 | query_database | 数据库结构查询 |
| 知识库 | query_knowledge_base | 业务术语、功能树查询 |
| 代码仓库 | clone_repository | Git 仓库克隆 |
| 结构分析 | extract_structure, extract_lookup_values | 代码结构提取 |
| 命令执行 | run_command | Shell 命令执行 |

## 工具组合推荐

系统预定义了常用工具组合：

- **设计文档生成**: `query_knowledge_base` → `read_file_chunk` → `write_file`
- **数据模型设计**: `query_database` → `query_knowledge_base` → `write_file`
- **API 设计**: `clone_repository` → `query_database` → `query_knowledge_base` → `write_file`
- **架构分析**: `clone_repository` → `extract_structure` → `grep_search` → `write_file`

## 注意事项

1. **系统保护**: Expert Creator 是系统专家，不可通过前端删除
2. **工具验证**: 新工具需要同时在 `protocol.py` 中实现处理函数
3. **LLM 回退**: 如果 LLM 生成失败，系统会使用预定义的模板生成默认内容
4. **唯一 ID**: 如果专家 ID 已存在，会自动添加随机后缀确保唯一性

## 更新日志

### v1.0.0 (2026-03-19)
- 重构为LLM指令驱动架构
- SKILL.md 作为LLM的主要指令文件
- 简化 generate_expert.py，移除硬编码prompt
- 添加 SKILL.md 模板文件
- UI分离：从专家列表移至"系统工具"区域
- 重命名为"Expert Architect / 专家构建器"
- 简化 expert-creator.expert.yaml 配置
- 新增系统工具注册中心 TOOL_REGISTRY.yaml
- 新增智能工具推荐功能
- 新增工具管理脚本 tool_manager.py
