---
name: api-design
description: 生成并校验项目级 API 设计产物，包含 HTTP API 契约与 RFC 9457 风格错误定义。支持根据受众（内部/外部/两者）自动判定并产出对应的 API 契约文件。
---

# 工作流 (Workflow)
1. 在生成任何产物前，必须先读取需求基线和现有接口资产。
2. **受众判定**：根据需求描述或 `audience` 输入，判定 API 的开放范围（内部：`internal`，外部：`external`，或两者：`both`）。
3. 复用 `assets/templates/` 中的模板（`api-internal.yaml` 或 `api-public.yaml`），仅填充必需的占位符。
4. 默认根据判定结果输出 `artifacts/api-internal.yaml`、`artifacts/api-public.yaml`、错误定义 `artifacts/errors-rfc9457.json` 以及阅读摘要 `artifacts/api-design.md`。
5. 将设计依据（如：参考了哪个文档、哪个 DDL）和工具校验结果记录到 `evidence/api-design.json` 中。
6. 如果缺少必需的输入参数，或者生成的产物无法满足输出契约（Output Contract），应直接终止并报错。

# 输入参数 (Inputs)
- `requirements`: 与 API 相关的项目需求描述。
- `existing_assets`: 现有的接口文档、网关路由配置、响应示例或代码入口。
- `output_root`: 项目设计包的根路径。
- `audience` (可选): 指定受众类型，可选值为 `internal`, `external`, `both`。默认为 `both`。

# 输出契约 (Output Contract)
- `artifacts/api-internal.yaml` (当受众包含 internal 时)
- `artifacts/api-public.yaml` (当受众包含 external 时)
- `artifacts/errors-rfc9457.json`
- `artifacts/api-design.md`
- `evidence/api-design.json`

# 工具集 (Tools)
- `python:design-system/skills/api-design/scripts/render_contract_stub.py`
- `spectral`
- `ajv`

# 参考资料 (References)
- 阅读 `references/api-style-guide.md` 以获取具体的命名和契约设计规则。
- 复用 `assets/templates/api-internal.yaml`、`assets/templates/api-public.yaml` 与 `assets/templates/errors-rfc9457.json` 模板。

# 注意事项 (Notes)
- 无论是内部还是外部同步 HTTP API，都统一使用 API 契约表达；其核心差异体现在使用受众、暴露的路径范围、安全策略及生成的文件名上。
- **外部 API 规范**：外部 API 设计应更加注重稳定性和安全性，避免暴露内部实现细节。
- 严禁编造需求或虚构错误语义，所有设计必须以现有资产和需求基线为准。
