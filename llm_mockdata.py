import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


HOST = "127.0.0.1"
PORT = 11433
MODEL_ID = "mock-llm-data"


def _json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _extract_messages(payload: dict[str, Any]) -> tuple[str, str]:
    messages = payload.get("messages", [])
    system_parts: list[str] = []
    user_parts: list[str] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            content = "\n".join(text_parts)
        content = str(content)
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            user_parts.append(content)
    return "\n".join(system_parts), "\n".join(user_parts)


def _extract_payload_from_user_prompt(user_prompt: str) -> dict[str, Any]:
    match = re.search(r"(\{[\s\S]*\})\s*$", user_prompt)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def _sanitize_token(value: str, fallback: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]+", "", value or "")
    return clean or fallback


def _to_snake(value: str, fallback: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return clean or fallback


def _mock_intent(requirement_text: str) -> dict[str, Any]:
    project_hint = _sanitize_token(requirement_text[:24], "MockDesign")
    return {
        "project_name": f"{project_hint}Platform",
        "project_id": "PRJ-MOCK-001",
        "version": "1.0.0",
        "server_url": "https://api.mock.internal",
        "owner": "design-platform-team",
        "audience": "both",
        "domain_name": "MockDomain",
        "aggregate_root": "MockAggregate",
        "scenario_name": "MockScenario",
        "scenario_desc": f"Generated from requirement: {requirement_text[:80]}",
        "entity_name": "MockEntity",
        "integration_scenario": "MockIntegration",
        "consumer": "MockConsumer",
        "provider": "MockProvider",
        "dependencies": "PostgreSQL, Redis, Kafka",
        "required_subagents": [
            "architecture-mapping",
            "api-design",
            "data-design",
            "flow-design",
            "ddd-structure",
            "integration-design",
            "config-design",
            "test-design",
            "ops-readiness",
        ],
    }


def _extract_expected_files(system_prompt: str) -> list[str]:
    patterns = [
        r'"([^"\n]+\.(?:md|json|yaml|sql))"',
        r"`([^`\n]+\.(?:md|json|yaml|sql))`",
        r"\b([A-Za-z0-9._-]+\.(?:md|json|yaml|sql))\b",
    ]
    found: list[str] = []
    for pattern in patterns:
        for item in re.findall(pattern, system_prompt, flags=re.IGNORECASE):
            if item not in found:
                found.append(item)
    return found


def _artifact_content(filename: str, context: dict[str, Any]) -> str:
    project_name = context.get("project_name", "MockDesignPlatform")
    scenario_name = context.get("scenario_name", "MockScenario")
    scenario_desc = context.get("scenario_desc", "Mock scenario for end-to-end validation.")
    entity_name = context.get("entity_name", "MockEntity")
    aggregate_root = context.get("aggregate_root", entity_name)
    domain_name = context.get("domain_name", "MockDomain")
    provider = context.get("provider", "MockProvider")
    audience = context.get("audience", "both")
    slug = _to_snake(project_name, "mock_design_platform")

    if filename == "schema.sql":
        return (
            f"CREATE TABLE {slug}_{_to_snake(entity_name, 'entity')} (\n"
            "  id BIGSERIAL PRIMARY KEY,\n"
            "  business_key VARCHAR(64) NOT NULL UNIQUE,\n"
            "  status VARCHAR(32) NOT NULL,\n"
            "  payload JSONB NOT NULL,\n"
            "  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,\n"
            "  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP\n"
            ");\n"
        )
    if filename == "er.md":
        return (
            "```mermaid\n"
            "erDiagram\n"
            f"    {aggregate_root.upper()} ||--o{{ {entity_name.upper()} : contains\n"
            f"    {aggregate_root.upper()} {{\n"
            "        string id\n"
            "        string business_key\n"
            "        string status\n"
            "    }\n"
            f"    {entity_name.upper()} {{\n"
            "        string id\n"
            "        json payload\n"
            "    }\n"
            "```\n"
        )
    if filename == "migration-plan.md":
        return (
            f"# Migration Plan for {project_name}\n\n"
            "1. Create baseline tables and indexes.\n"
            "2. Backfill core business records from the source system.\n"
            "3. Enable dual-write verification for one release window.\n"
            "4. Cut over reads after data reconciliation passes.\n"
        )
    if filename.endswith(".yaml") and filename.startswith("api-"):
        return (
            "openapi: 3.1.0\n"
            "info:\n"
            f"  title: {project_name} API\n"
            "  version: 1.0.0\n"
            "paths:\n"
            f"  /api/{slug}/{_to_snake(scenario_name, 'scenario')}:\n"
            "    post:\n"
            f"      summary: Trigger {scenario_name}\n"
            "      responses:\n"
            "        '200':\n"
            "          description: success\n"
        )
    if filename == "errors-rfc9457.json":
        return json.dumps(
            {
                "type": "https://example.com/problems/validation-error",
                "title": "Validation error",
                "status": 400,
                "detail": f"{project_name} rejected the request payload.",
            },
            ensure_ascii=False,
            indent=2,
        )
    if filename == "module-map.json":
        return json.dumps(
            {
                "project": project_name,
                "modules": [
                    {"name": "api-gateway", "responsibility": "request routing"},
                    {"name": domain_name, "responsibility": scenario_desc},
                    {"name": "integration-adapter", "responsibility": f"connect to {provider}"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    if filename == "config-catalog.yaml":
        return (
            "config:\n"
            "  APP_ENV:\n"
            "    required: true\n"
            "  DATABASE_URL:\n"
            "    required: true\n"
            "  FEATURE_TOGGLE_MAIN_FLOW:\n"
            "    required: false\n"
        )
    if filename == "traceability.json":
        return json.dumps(
            {
                "requirement": scenario_desc,
                "mapped_artifacts": ["api-design.md", "schema.sql", "detailed-design.md"],
                "audience": audience,
            },
            ensure_ascii=False,
            indent=2,
        )
    if filename == "coverage-map.json":
        return json.dumps(
            {
                "scenario": scenario_name,
                "coverage": [
                    {"type": "happy_path", "status": "covered"},
                    {"type": "integration_failure", "status": "covered"},
                    {"type": "concurrency", "status": "covered"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    if filename == "asyncapi.yaml":
        return (
            "asyncapi: '2.6.0'\n"
            "info:\n"
            f"  title: {project_name} Integration Events\n"
            "  version: 1.0.0\n"
            "channels:\n"
            f"  {slug}.events:\n"
            "    publish:\n"
            "      message:\n"
            "        name: MockEvent\n"
        )
    if filename == "slo.yaml":
        return (
            "slos:\n"
            "  - name: request-success-rate\n"
            "    objective: 99.9\n"
            "  - name: p95-latency-ms\n"
            "    objective: 300\n"
        )
    if filename == "observability-spec.yaml":
        return (
            "metrics:\n"
            "  - request_total\n"
            "  - request_error_total\n"
            "  - request_latency_ms\n"
            "traces:\n"
            f"  - external_call:{provider}\n"
        )
    if filename.endswith(".json"):
        return json.dumps(
            {
                "project": project_name,
                "scenario": scenario_name,
                "file": filename,
                "status": "mocked",
            },
            ensure_ascii=False,
            indent=2,
        )
    if filename.endswith(".sql"):
        return f"-- Mock SQL for {project_name}\nSELECT 1;\n"
    if filename.endswith(".yaml"):
        return f"name: {project_name}\nscenario: {scenario_name}\nstatus: mocked\n"
    return (
        f"# {filename}\n\n"
        f"- project: {project_name}\n"
        f"- scenario: {scenario_name}\n"
        f"- aggregate: {aggregate_root}\n"
        f"- note: mock artifact generated for end-to-end validation.\n"
    )


def _mock_artifacts(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    context = _extract_payload_from_user_prompt(user_prompt)
    files = _extract_expected_files(system_prompt)
    if not files:
        files = ["design-output.md"]

    artifacts = {name: _artifact_content(name, context) for name in files}
    reasoning = (
        "This response was generated by llm_mockdata.py. "
        "It returns deterministic mock artifacts so the agent workflow can be validated quickly."
    )
    return {"reasoning": reasoning, "artifacts": artifacts}


class MockHandler(BaseHTTPRequestHandler):
    server_version = "llm_mockdata/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path in ("/", "/health", "/healthz"):
            _json_response(
                self,
                {
                    "service": "llm_mockdata",
                    "status": "ok",
                    "base_url": f"http://{HOST}:{PORT}/v1",
                    "model": MODEL_ID,
                },
            )
            return
        if self.path == "/v1/models":
            _json_response(
                self,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": MODEL_ID,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "local-mock",
                        }
                    ],
                },
            )
            return
        _json_response(self, {"error": {"message": f"Unsupported path: {self.path}"}}, status=404)

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            _json_response(self, {"error": {"message": f"Unsupported path: {self.path}"}}, status=404)
            return

        payload = _read_json(self)
        system_prompt, user_prompt = _extract_messages(payload)
        is_intent_request = "required_subagents" in system_prompt or "DesignIntent" in system_prompt

        if is_intent_request:
            content = json.dumps(_mock_intent(user_prompt), ensure_ascii=False)
        else:
            content = json.dumps(_mock_artifacts(system_prompt, user_prompt), ensure_ascii=False)

        response = {
            "id": f"chatcmpl-mock-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", MODEL_ID),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 128,
                "completion_tokens": max(32, len(content) // 4),
                "total_tokens": 128 + max(32, len(content) // 4),
            },
        }
        _json_response(self, response)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), MockHandler)
    print(f"llm_mockdata listening on http://{HOST}:{PORT}/v1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
