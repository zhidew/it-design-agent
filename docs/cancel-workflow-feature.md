# 流水线停止和重试功能实现

## 功能概述

为编排引擎流水线添加了停止按钮，允许用户在节点执行过慢时中断执行，然后可以选择不同的LLM模型或强度重新执行。

## 后端修改

### 1. 新增 CancelRequest 模型
**文件**: `api_server/models/project.py`

```python
class CancelRequest(BaseModel):
    reason: Optional[str] = None
```

### 2. 新增 cancel_workflow 函数
**文件**: `api_server/services/orchestrator_service.py`

- 取消正在运行的任务
- 将正在运行的任务状态重置为 "todo"
- 将工作流状态设置为 "waiting_human"
- 设置取消原因和恢复提示

### 3. 修改 continue_workflow 函数
**文件**: `api_server/services/orchestrator_service.py`

- 支持从 "waiting_human" 状态（取消后）继续执行
- 允许传递新的 model 和 effort_level 参数

### 4. 新增 /cancel API 端点
**文件**: `api_server/routers/projects.py`

```python
@router.post("/{project_id}/versions/{version}/cancel")
async def cancel_workflow(project_id: str, version: str, req: CancelRequest):
```

## 前端修改

### 1. 新增 cancelWorkflow API
**文件**: `admin-ui/src/api.ts`

```typescript
cancelWorkflow: (projectId: string, version: string, reason?: string) =>
  apiClient.post(`/projects/${projectId}/versions/${version}/cancel`, { reason }).then(res => res.data),
```

### 2. 添加停止按钮
**文件**: `admin-ui/src/components/ProjectDetail.tsx`

- 在运行状态时显示红色停止按钮
- 点击后确认取消

### 3. 取消后重试界面
**文件**: `admin-ui/src/components/ProjectDetail.tsx`

- 取消后显示专门的恢复面板（玫瑰色主题）
- 提供 LLM 模型选择（Claude、GPT等）
- 提供强度选择（Low/Medium/High/Ultra）
- 显示当前配置参数

## 使用流程

1. **运行时停止**: 当流水线执行时，点击 "Stop Workflow" 按钮
2. **确认取消**: 弹出确认对话框
3. **重新配置**: 取消后，界面显示"Workflow Cancelled"面板
4. **选择参数**: 选择新的 LLM 模型和执行强度
5. **重新执行**: 点击 "Retry with New Settings" 按钮

## API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/v1/projects/{id}/versions/{ver}/cancel | 取消工作流 |
| POST | /api/v1/projects/{id}/versions/{ver}/continue | 继续执行（支持新参数） |
