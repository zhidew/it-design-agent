# IT Design Agent

> 企业级IT详细设计自动化平台 - 基于LangGraph的多智能体编排系统

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19+-blue.svg)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-latest-orange.svg)](https://github.com/langchain-ai/langgraph)

## 📋 项目简介

IT Design Agent 是一个基于大语言模型（LLM）的企业级IT详细设计自动化平台。通过多智能体协作，自动生成符合企业规范的详细设计文档，包括：

- **架构设计** - 模块边界、依赖关系、架构图
- **领域建模** - DDD结构、聚合定义、领域模型
- **数据设计** - 数据库schema、迁移计划、ER图
- **接口设计** - OpenAPI规范、错误码体系、接口文档
- **流程设计** - 时序图、状态机、业务流程
- **集成设计** - 外部系统对接、事件契约
- **配置设计** - 配置矩阵、开关策略
- **测试设计** - 测试策略、用例设计
- **运维就绪** - SLO定义、可观测性方案

## ✨ 核心特性

- 🤖 **多智能体协作** - 基于LangGraph的专家编排系统，支持并行执行和依赖管理
- 📝 **设计产物自动生成** - 自动生成符合企业标准的详细设计文档
- 🔄 **版本管理** - 支持设计迭代和版本回溯
- 🎯 **质量门禁** - 内置设计验证和质量检查
- 🌐 **Web界面** - 现代化的管理界面，支持实时预览和交互
- 🔌 **可扩展** - 灵活的专家配置系统，支持自定义技能
- 🌍 **国际化** - 支持中文/英文双语界面

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (React)                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ 项目管理  │  │ 专家中心  │  │ 设计工作台│         │
│  └──────────┘  └──────────┘  └──────────┘         │
└─────────────────────┬───────────────────────────────┘
                      │ HTTP/SSE
┌─────────────────────┴───────────────────────────────┐
│                Backend (FastAPI)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │   API    │  │ Orchestrator│ │ Registry │         │
│  │ Routers  │  │   Service   │ │ Service  │         │
│  └──────────┘  └──────────┘  └──────────┘         │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────┐
│              LangGraph Agent System                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ Planner  │─▶│ Experts  │─▶│Validator │         │
│  └──────────┘  └──────────┘  └──────────┘         │
└─────────────────────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────┐
│            External Resources & Tools                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │Database  │  │ Git Repo │  │Knowledge │         │
│  └──────────┘  └──────────┘  └──────────┘         │
└─────────────────────────────────────────────────────┘
```

## 📦 项目结构

```
it-design-agent/
├── api_server/           # 后端服务
│   ├── main.py          # FastAPI应用入口
│   ├── graphs/          # LangGraph图定义
│   ├── routers/         # API路由
│   ├── services/        # 业务逻辑
│   ├── registry/        # 专家注册中心
│   └── models/          # 数据模型
├── admin-ui/            # 前端应用
│   ├── src/            # 源代码
│   ├── public/         # 静态资源
│   └── package.json    # 依赖配置
├── skills/              # 专家技能定义
│   ├── api-design/     # API设计专家
│   ├── data-design/    # 数据设计专家
│   └── ...             # 其他专家
├── experts/             # 专家配置文件
├── projects/            # 项目数据目录
├── scripts/             # 工具脚本
├── docs/                # 文档
└── schemas/             # Schema定义
```

## 🚀 快速开始

### 前置要求

- **Python** 3.11 或更高版本
- **Node.js** 18 或更高版本
- **PostgreSQL** / **MySQL** / **SQLite** (可选，用于数据库元数据)

### Windows快速启动

1. **克隆项目**
```bash
git clone <repository-url>
cd it-design-agent
```

2. **配置环境变量**
```bash
# 复制环境变量模板
copy .env.example .env

# 编辑.env文件，配置必要的参数
# LLM_PROVIDER=openai  # 或 gemini
# OPENAI_API_KEY=your-api-key
# OPENAI_MODEL=gpt-4
```

3. **一键启动**
```bash
# 双击运行
start-all.bat

# 或单独启动
start-backend.bat   # 启动后端
start-frontend.bat  # 启动前端
```

4. **访问应用**
- 前端界面: http://localhost:5173
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

### 手动启动（跨平台）

#### 后端

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 安装依赖
pip install -r api_server/requirements.txt

# 启动服务
cd api_server
python main.py
```

#### 前端

```bash
cd admin-ui

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

## 📖 使用指南

### 1. 创建项目

1. 访问前端界面，点击"创建项目"
2. 输入项目名称和描述
3. 进入项目工作空间

### 2. 配置资源

在项目配置页面设置：
- **代码仓库** - Git仓库访问配置
- **数据库** - 数据库连接配置
- **知识库** - 参考文档和术语表
- **专家启用** - 选择需要启用的设计专家

### 3. 启动设计

1. 创建新的设计版本
2. 输入需求描述或上传需求文档
3. 点击"启动编排"
4. 实时查看专家执行过程
5. 查看生成的设计产物

### 4. 专家中心

在专家中心管理设计专家：
- 查看专家配置和技能
- 编辑专家模板和参考文档
- 查看工具清单（expert-creator）
- 创建新的自定义专家

## 🛠️ 配置说明

### 环境变量

```bash
# LLM配置
LLM_PROVIDER=openai           # LLM提供商: openai | gemini
OPENAI_API_KEY=sk-xxx        # OpenAI API密钥
OPENAI_MODEL=gpt-4           # 模型名称
OPENAI_BASE_URL=             # 自定义API地址（可选）

# Gemini配置（如果使用Gemini）
GOOGLE_API_KEY=xxx           # Google API密钥

# 项目配置
PROJECTS_DIR=./projects       # 项目数据目录

# 安全配置（可选）
IT_DESIGN_AGENT_METADATA_KEY= # 元数据加密密钥
```

### 专家配置

每个专家包含以下配置文件：

```yaml
experts/
  api-design.expert.yaml      # 专家元数据
skills/
  api-design/
    SKILL.md                  # 技能定义和工作流
    templates/                # 输出模板
    references/               # 参考文档
    scripts/                  # 辅助脚本
```

## 🔧 开发指南

### 添加新专家

1. 创建专家目录：`skills/your-expert/`
2. 编写技能定义：`SKILL.md`
3. 创建配置文件：`experts/your-expert.expert.yaml`
4. 添加模板和参考文档

### 扩展工具

在 `api_server/graphs/tools/` 下添加新工具：

```python
# my_tool.py
from .protocol import ToolResult

def execute_my_tool(param: str) -> ToolResult:
    """工具描述"""
    # 实现工具逻辑
    return ToolResult(output="result")
```

### API开发

参考现有的router实现：

```python
# api_server/routers/my_router.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/my-resource", tags=["MyResource"])

@router.get("")
async def list_items():
    return {"items": []}
```

## 📊 核心概念

### 专家 (Expert)

专家是具备特定设计能力的智能体，每个专家负责一个设计领域。系统内置专家包括：

| 专家 | 职责 | 输出产物 |
|------|------|----------|
| api-design | API接口设计 | api-internal.yaml, errors-rfc9457.json |
| data-design | 数据模型设计 | schema.sql, er.md, migration-plan.md |
| ddd-structure | 领域模型设计 | ddd-structure.md |
| architecture-mapping | 架构设计 | architecture.md |
| flow-design | 流程设计 | sequence-*.md, state-*.md |
| integration-design | 集成设计 | integration-*.md |
| config-design | 配置设计 | config-matrix.md |
| test-design | 测试设计 | test-strategy.md |
| ops-design | 运维就绪 | slo.yaml, observability.yaml |
| design-assembler | 设计汇编 | detailed-design.md |
| validator | 设计验证 | validation-report.json |

### 编排流程

```
需求输入 → Planner分解 → 专家并行执行 → Validator验证 → 产物输出
```

### 工具系统

专家可使用的内置工具：
- `clone_repository` - 克隆代码仓库
- `query_database` - 查询数据库元数据
- `query_knowledge_base` - 查询知识库
- `read_file_chunk` - 读取文件片段
- `write_file` - 写入文件
- `patch_file` - 修改文件
- `list_files` - 列出文件
- `grep_search` - 搜索文件内容
- `run_command` - 执行命令

## 🧪 测试

```bash
# 运行后端测试
cd api_server
pytest tests/

# 运行前端测试
cd admin-ui
npm run test
```

## 📝 更新日志

### v0.1.0 (2026-03)
- ✨ 初始版本发布
- ✅ 实现多智能体编排系统
- ✅ 完成前端管理界面
- ✅ 支持设计产物自动生成
- ✅ 实现专家配置系统

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

1. Fork本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [LangChain](https://github.com/langchain-ai/langchain) - LLM应用框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - 智能体编排
- [FastAPI](https://fastapi.tiangolo.com/) - Web框架
- [React](https://react.dev/) - 前端框架
- [Tailwind CSS](https://tailwindcss.com/) - UI框架

## 📞 联系方式

- 项目主页: <repository-url>
- 问题反馈: <repository-url>/issues
- 文档: <repository-url>/wiki

---

**注意**: 本项目仅供学习和研究使用，生产环境使用请谨慎评估。
