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

class SubagentOutput(BaseModel):
    reasoning: str = Field(description="LLM reasoning process and decision logic (Markdown format)")
    artifacts: dict[str, str] = Field(description="Generated files dictionary, key is filename, value is content.")

from services.log_service import save_llm_interaction

BASE_DIR = Path(__file__).resolve().parent.parent.parent

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
            if project_id and version:
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
                    include_full_artifacts=include_full_artifacts_in_log
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
            if project_id and version:
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
                    error=f"JSONDecodeError: {str(e)}"
                )
            time.sleep(2)
        except Exception as e:
            last_error = e
            print(f"  [LLM Service] Data validation/call failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
            if project_id and version:
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
                    error=f"Exception: {str(e)}"
                )
            time.sleep(2)
            
    raise Exception(f"LLM generation failed after {max_retries} retries. Last error: {last_error}")

def _clean_json_response(text: str) -> str:
    text = text.strip()
    # Remove potential ```json ... ``` wrapper
    if text.startswith("```"):
        first_newline = text.find('\n')
        if first_newline != -1:
            text = text[first_newline:]
        else:
            text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def _call_gemini_raw(system_prompt: str, user_prompt: str, llm_settings: dict | None = None) -> dict:
    import google.generativeai as genai
    api_key = _resolve_llm_setting(llm_settings, "gemini_api_key", "GEMINI_API_KEY")
    model_name = _resolve_llm_setting(llm_settings, "gemini_model_name", "GEMINI_MODEL_NAME", "gemini-2.0-flash")
    genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel(
        model_name,
        system_instruction=system_prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    response = model.generate_content(user_prompt)
    raw_text = _clean_json_response(response.text)
    return json.loads(raw_text)

def _call_openai_raw(system_prompt: str, user_prompt: str, llm_settings: dict | None = None) -> dict:
    from openai import OpenAI
    api_key = _resolve_llm_setting(llm_settings, "openai_api_key", "OPENAI_API_KEY")
    base_url = _resolve_llm_setting(llm_settings, "openai_base_url", "OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = _resolve_llm_setting(llm_settings, "openai_model_name", "OPENAI_MODEL_NAME", "gpt-4o")
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"}
    )
    raw_text = _clean_json_response(completion.choices[0].message.content)
    return json.loads(raw_text)
