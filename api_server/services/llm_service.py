import os
import json
import time
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pathlib import Path

# Ensure .env file is loaded from project root
root_env = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=root_env)

def _resolve_llm_setting(llm_settings: dict | None, key: str, env_key: str, default: str = "") -> str:
    if llm_settings and llm_settings.get(key) not in (None, ""):
        return str(llm_settings.get(key))
    return os.getenv(env_key, default)

def _resolve_llm_dict_setting(llm_settings: dict | None, key: str) -> dict[str, str] | None:
    if not llm_settings:
        return None
    value = llm_settings.get(key)
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    return None

class SubagentOutput(BaseModel):
    reasoning: str = Field(description="LLM reasoning process and decision logic (Markdown format)")
    artifacts: dict[str, str] = Field(description="Generated files dictionary, key is filename, value is content.")

from services.log_service import save_llm_interaction
from services.db_service import metadata_db

BASE_DIR = Path(__file__).resolve().parent.parent.parent

def resolve_runtime_llm_settings(design_context: dict | None) -> dict | None:
    """
    Normalize a runtime-selected model config into llm_settings expected by
    generate_with_llm().
    """
    model_config = (design_context or {}).get("model_config") or {}
    provider = str(model_config.get("provider") or "").strip().lower()
    api_key = model_config.get("api_key")
    model_name = model_config.get("model_name")
    base_url = model_config.get("base_url")

    # Keep runtime model selection active even when the chosen config relies on
    # gateway headers or a local proxy instead of an explicit API key.
    if not provider or not model_name:
        return None

    if provider == "gemini":
        return {
            "llm_provider": "gemini",
            "gemini_api_key": api_key,
            "gemini_model_name": model_name,
        }

    return {
        "llm_provider": "openai",
        "openai_api_key": api_key,
        "openai_base_url": base_url,
        "openai_model_name": model_name,
        "openai_headers": model_config.get("headers"),
    }

def generate_with_llm(
    system_prompt: str,
    user_prompt: str,
    expected_files: list[str],
    max_retries: int = 2,
    llm_settings: dict | None = None,
    project_id: str | None = None,
    version: str | None = None,
    node_id: str | None = None,
    include_full_artifacts_in_log: bool = False,
) -> SubagentOutput:
    """
    Generic LLM generator that enforces output containing reasoning log and specified file contents in JSON.
    """
    provider = _resolve_llm_setting(llm_settings, "llm_provider", "LLM_PROVIDER", "openai").lower()
    
    # Dynamically build output constraints
    file_schema_desc = "Generated artifact file contents. Must include the following keys: " + ", ".join(expected_files)
    
    enhanced_system_prompt = system_prompt + f"""
    
    [Mandatory Output Specification]
    You must output only a valid JSON string strictly conforming to the following Schema:
    {{
        "reasoning": "Your reasoning process...",
        "artifacts": {{
            "{expected_files[0]}": "Complete content of file 1...",
            ...
        }}
    }}
    Ensure the artifacts dictionary contains all required files with usable, compliant content. Do NOT output extra Markdown code block symbols (like ```json).
    """

    last_error = None
    model_name = ""
    debug_config = metadata_db.get_project_debug_config(project_id) if project_id else None
    llm_interaction_logging_enabled = bool((debug_config or {}).get("llm_interaction_logging_enabled"))
    llm_full_payload_logging_enabled = bool((debug_config or {}).get("llm_full_payload_logging_enabled"))
    if provider == "gemini":
        model_name = _resolve_llm_setting(llm_settings, "gemini_model_name", "GEMINI_MODEL_NAME", "gemini-2.0-flash")
    else:
        model_name = _resolve_llm_setting(llm_settings, "openai_model_name", "OPENAI_MODEL_NAME", "gpt-4o")

    for attempt in range(max_retries + 1):
        try:
            raw_data = None
            if provider == "gemini":
                raw_data = _call_gemini_raw(enhanced_system_prompt, user_prompt, llm_settings=llm_settings)
            else:
                raw_data = _call_openai_raw(enhanced_system_prompt, user_prompt, llm_settings=llm_settings)
            
            # Log interaction if project info is provided
            if project_id and version and llm_interaction_logging_enabled:
                save_llm_interaction(
                    project_id=project_id,
                    version=version,
                    base_dir=BASE_DIR,
                    node_id=node_id or "unknown",
                    system_prompt=enhanced_system_prompt,
                    user_prompt=user_prompt,
                    response=raw_data,
                    provider=provider,
                    model=model_name,
                    status="success",
                    include_full_artifacts=include_full_artifacts_in_log,
                    persist_payload_files=llm_full_payload_logging_enabled,
                )

            # --- Robust data repair logic ---
            # 1. Ensure artifacts is a dict
            artifacts = raw_data.get("artifacts", {})
            if not isinstance(artifacts, dict):
                artifacts = {}
            
            # 2. Fix nested dict issues
            fixed_artifacts = {}
            for k, v in artifacts.items():
                if isinstance(v, (dict, list)):
                    # If LLM outputs nested JSON, convert back to string
                    fixed_artifacts[k] = json.dumps(v, ensure_ascii=False, indent=2)
                else:
                    fixed_artifacts[k] = str(v)
            
            # 3. Fill missing expected files
            for f in expected_files:
                if f not in fixed_artifacts:
                    fixed_artifacts[f] = ""
            
            raw_data["artifacts"] = fixed_artifacts
            
            # 4. Provide default reasoning if missing
            if "reasoning" not in raw_data:
                raw_data["reasoning"] = "No reasoning provided by LLM."

            return SubagentOutput.model_validate(raw_data)

        except json.JSONDecodeError as e:
            last_error = e
            print(f"  [LLM Service] JSON parse failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
            if project_id and version and llm_interaction_logging_enabled:
                save_llm_interaction(
                    project_id=project_id,
                    version=version,
                    base_dir=BASE_DIR,
                    node_id=node_id or "unknown",
                    system_prompt=enhanced_system_prompt,
                    user_prompt=user_prompt,
                    response=None,
                    provider=provider,
                    model=model_name,
                    status="error",
                    error=f"JSONDecodeError: {str(e)}",
                    persist_payload_files=llm_full_payload_logging_enabled,
                )
            time.sleep(2)
        except Exception as e:
            last_error = e
            print(f"  [LLM Service] Data validation/call failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
            if project_id and version and llm_interaction_logging_enabled:
                save_llm_interaction(
                    project_id=project_id,
                    version=version,
                    base_dir=BASE_DIR,
                    node_id=node_id or "unknown",
                    system_prompt=enhanced_system_prompt,
                    user_prompt=user_prompt,
                    response=None,
                    provider=provider,
                    model=model_name,
                    status="error",
                    error=f"Exception: {str(e)}",
                    persist_payload_files=llm_full_payload_logging_enabled,
                )
            time.sleep(2)
            
    raise Exception(f"LLM generation failed after {max_retries} retries. Last error: {last_error}")

import re

def _clean_json_response(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    
    # Handle SSE 'data:' prefix if the whole string is prefixed
    if text.startswith("data:"):
        text = text[5:].strip()

    # Remove potential ```json ... ``` wrapper
    # We use regex to be more robust with multi-line content
    json_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if json_block_match:
        text = json_block_match.group(1)
        
    return text.strip()

def _parse_llm_response_to_dict(completion) -> dict:
    """
    Robustly extracts the JSON dictionary from an LLM completion object or string.
    Handles standard OpenAI objects, SSE-prefixed strings, and raw JSON strings.
    """
    import json
    
    # 1. Try standard access (OpenAI SDK Object)
    if hasattr(completion, "choices") and completion.choices:
        content = completion.choices[0].message.content
        if content:
            return json.loads(_clean_json_response(content))
            
    # 2. Handle string or dict-like responses
    raw_text = str(completion).strip()
    if raw_text.startswith("data:"):
        raw_text = raw_text[5:].strip()
        
    # Try to parse the entire string as a JSON (it might be the full response object as a string)
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            # If it's the full response object, try to find the content in choices
            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                if isinstance(choice, dict):
                    msg = choice.get("message", {})
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
                    if content:
                        return json.loads(_clean_json_response(content))
            # Maybe the whole thing is already the JSON we want (the model's direct output)
            return data
    except:
        pass
        
    # 3. Last resort: treat the raw text as the JSON content directly
    return json.loads(_clean_json_response(raw_text))

def _call_gemini_raw(system_prompt: str, user_prompt: str, llm_settings: dict | None = None) -> dict:
    import google.generativeai as genai
    api_key = _resolve_llm_setting(llm_settings, "gemini_api_key", "GEMINI_API_KEY")
    model_name = _resolve_llm_setting(llm_settings, "gemini_model_name", "GEMINI_MODEL_NAME", "gemini-2.0-flash")
    
    # Use placeholder if key is missing to support local/no-auth gateways
    genai.configure(api_key=api_key or "not-required")
    
    model = genai.GenerativeModel(
        model_name,
        system_instruction=system_prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    response = model.generate_content(user_prompt)
    # Use robust parsing
    return _parse_llm_response_to_dict(response.text)

def test_llm_connectivity(llm_settings: dict) -> dict:
    """
    Test the connectivity and availability of an LLM configuration.
    Returns a dict with success status and message.
    """
    provider = llm_settings.get("provider", "openai").lower()
    try:
        if provider == "gemini":
            import google.generativeai as genai
            api_key = llm_settings.get("api_key")
            model_name = llm_settings.get("model_name", "gemini-2.0-flash")
            
            # Allow empty API key if using a custom gateway or local provider
            genai.configure(api_key=api_key or "not-required")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("Ping")
            if response and response.text:
                return {"success": True, "message": "Connected successfully to Gemini."}
            return {"success": False, "message": "Received empty response from Gemini."}
        else:
            from openai import OpenAI
            api_key = llm_settings.get("api_key")
            base_url = llm_settings.get("base_url", "https://api.openai.com/v1")
            model_name = llm_settings.get("model_name", "gpt-4o")
            headers = llm_settings.get("headers") or {}
            
            # If user already provided Authorization in headers, we avoid providing a dummy key
            # to let the custom header take precedence.
            has_auth_header = any(k.lower() == "authorization" for k in headers.keys())
            effective_api_key = api_key
            if not effective_api_key and not has_auth_header:
                effective_api_key = "not-required"
            
            client = OpenAI(api_key=effective_api_key or "", base_url=base_url, default_headers=headers or None)
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "Ping"}],
                max_tokens=5
            )
            
            # Use robust parsing logic for connectivity test
            try:
                res_dict = _parse_llm_response_to_dict(completion)
                if res_dict or completion:
                    return {"success": True, "message": f"Connected successfully to {provider.upper()} compatible API (Robust parsing enabled)."}
            except:
                pass

            return {
                "success": False, 
                "message": f"Invalid response format. Content: {str(completion)[:200]}"
            }
    except Exception as e:
        return {"success": False, "message": str(e)}

def _call_openai_raw(system_prompt: str, user_prompt: str, llm_settings: dict | None = None) -> dict:
    from openai import OpenAI
    api_key = _resolve_llm_setting(llm_settings, "openai_api_key", "OPENAI_API_KEY")
    base_url = _resolve_llm_setting(llm_settings, "openai_base_url", "OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = _resolve_llm_setting(llm_settings, "openai_model_name", "OPENAI_MODEL_NAME", "gpt-4o")
    headers = _resolve_llm_dict_setting(llm_settings, "openai_headers")
    
    # Use placeholder if key is missing to support local/no-auth gateways
    # Check if Auth header is already present
    has_auth_header = any(k.lower() == "authorization" for k in (headers or {}).keys())
    effective_api_key = api_key
    if not effective_api_key and not has_auth_header:
        effective_api_key = "not-required"

    client = OpenAI(api_key=effective_api_key or "", base_url=base_url, default_headers=headers or None)
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    # Use robust parsing for production design calls
    return _parse_llm_response_to_dict(completion)
