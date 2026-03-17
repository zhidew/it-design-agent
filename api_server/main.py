import asyncio
import sys
from pathlib import Path

# 将项目根目录 (it-design-agent) 加入 sys.path 以便导入 scripts
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

# Ensure ProactorEventLoop on Windows for subprocess support
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from models.events import dump_event, validate_event_payload
from routers import projects, management
from services import orchestrator_service as orch

# --- 巧妙的日志过滤器 ---
class PollingLogFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.state_poll_count = 0

    def filter(self, record):
        # 检查是否是 /state 接口的访问日志
        if "/state" in record.getMessage():
            self.state_poll_count += 1
            # 每 20 次轮询才打印一个打点，或者你可以完全返回 False 屏蔽
            if self.state_poll_count >= 20:
                print(".", end="", flush=True) # 在控制台打印一个点表示“心跳”
                self.state_poll_count = 0
            return False # 返回 False 表示不记录这条日志到标准输出
        return True

# 应用过滤器到 uvicorn 的访问日志
logging.getLogger("uvicorn.access").addFilter(PollingLogFilter())

app = FastAPI(
    title="IT Detailed Design Agent API",
    description="Backend API for the IT Detailed Design Agent UI",
    version="1.0.0",
)

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev only, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(management.router)

@app.get("/api/v1/jobs/{job_id}/status")
async def get_job_status_stream(request: Request, job_id: str):
    """
    Server-Sent Events (SSE) endpoint to stream structured orchestrator events.
    """
    async def event_generator():
        queue = None
        backlog = orch.get_job_events(job_id)
        for payload in backlog:
            if await request.is_disconnected():
                return
            event = validate_event_payload(payload)
            yield {"event": event.event_type, "data": json.dumps(dump_event(event), ensure_ascii=False)}

        queue = orch.subscribe_job_events(job_id)
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    continue

                event = validate_event_payload(payload)
                yield {"event": event.event_type, "data": json.dumps(dump_event(event), ensure_ascii=False)}

                if event.event_type in {"run_completed", "run_failed"}:
                    break
        finally:
            if queue is not None:
                orch.unsubscribe_job_events(job_id, queue)

    return EventSourceResponse(event_generator(), ping=15)

if __name__ == "__main__":
    import uvicorn
    # Make sure this is run from the design-system/api_server directory or set pythonpath
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
