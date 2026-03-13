import os
import json
import time
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pathlib import Path

# 确保能找到项目根目录下的 .env 文件
# it-design-agent/scripts/llm_generator.py -> parent is scripts -> parent is it-design-agent
root_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=root_env)

class SubagentOutput(BaseModel):
    reasoning: str = Field(description="大模型对该领域设计的思考过程和决策逻辑 (Markdown 格式)")
    artifacts: dict[str, str] = Field(description="生成的文件字典，键为文件名，值为文件内容。")

def generate_with_llm(system_prompt: str, user_prompt: str, expected_files: list[str], max_retries: int = 2) -> SubagentOutput:
    """
    通用的大模型生成器，强制输出包含推理日志和指定文件内容的 JSON。
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    # 动态构建输出约束
    file_schema_desc = "生成的具体产物文件内容。必须包含以下键: " + ", ".join(expected_files)
    
    enhanced_system_prompt = system_prompt + f"""
    
    【强制输出规范】
    你必须且只能输出合法的 JSON 字符串，严格符合以下 Schema：
    {{
        "reasoning": "你的思考过程...",
        "artifacts": {{
            "{expected_files[0]}": "文件 1 的完整内容...",
            ...
        }}
    }}
    请确保 artifacts 字典中包含了所有要求的文件，并且内容是可用的、符合规范的。绝对不要输出额外的 Markdown 代码块符号(如```json)。
    """

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            raw_data = None
            if provider == "gemini":
                raw_data = _call_gemini_raw(enhanced_system_prompt, user_prompt)
            else:
                raw_data = _call_openai_raw(enhanced_system_prompt, user_prompt)
            
            # --- 强健的数据修复逻辑 ---
            # 1. 确保 artifacts 是字典
            artifacts = raw_data.get("artifacts", {})
            if not isinstance(artifacts, dict):
                artifacts = {}
            
            # 2. 修复嵌套字典问题 (如用户遇到的报错)
            fixed_artifacts = {}
            for k, v in artifacts.items():
                if isinstance(v, (dict, list)):
                    # 如果 LLM 调皮输出了嵌套 JSON，我们将其转回字符串
                    fixed_artifacts[k] = json.dumps(v, ensure_ascii=False, indent=2)
                else:
                    fixed_artifacts[k] = str(v)
            
            # 3. 填充缺失的预期文件
            for f in expected_files:
                if f not in fixed_artifacts:
                    fixed_artifacts[f] = ""
            
            raw_data["artifacts"] = fixed_artifacts
            
            # 4. 如果 reasoning 缺失，给个默认值
            if "reasoning" not in raw_data:
                raw_data["reasoning"] = "No reasoning provided by LLM."

            return SubagentOutput.model_validate(raw_data)

        except json.JSONDecodeError as e:
            last_error = e
            print(f"  [LLM Generator] JSON 解析失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
            time.sleep(2)
        except Exception as e:
            last_error = e
            print(f"  [LLM Generator] 数据验证/调用失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
            time.sleep(2)
            
    raise Exception(f"大模型生成失败，已重试 {max_retries} 次。最后错误: {last_error}")

def _clean_json_response(text: str) -> str:
    text = text.strip()
    # 移除首尾可能的 ```json ... ```
    if text.startswith("```"):
        # 寻找第一个换行符
        first_newline = text.find('\n')
        if first_newline != -1:
            text = text[first_newline:]
        else:
            text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def _call_gemini_raw(system_prompt: str, user_prompt: str) -> dict:
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")
    genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel(
        model_name,
        system_instruction=system_prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    response = model.generate_content(user_prompt)
    raw_text = _clean_json_response(response.text)
    return json.loads(raw_text)

def _call_openai_raw(system_prompt: str, user_prompt: str) -> dict:
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
    
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
