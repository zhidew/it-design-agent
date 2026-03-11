import os
import json
import time
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

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
            if provider == "gemini":
                return _call_gemini(enhanced_system_prompt, user_prompt, expected_files)
            else:
                return _call_openai(enhanced_system_prompt, user_prompt)
        except json.JSONDecodeError as e:
            last_error = e
            print(f"  [LLM Generator] JSON 解析失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
            time.sleep(2)
        except Exception as e:
            last_error = e
            print(f"  [LLM Generator] 调用失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
            time.sleep(2)
            
    raise Exception(f"大模型生成失败，已重试 {max_retries} 次。最后错误: {last_error}")

def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def _call_gemini(system_prompt: str, user_prompt: str, expected_files: list) -> SubagentOutput:
    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning)
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel(
        model_name,
        system_instruction=system_prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    response = model.generate_content(user_prompt)
    raw_text = _clean_json_response(response.text)
    data = json.loads(raw_text)
    return SubagentOutput.model_validate(data)

def _call_openai(system_prompt: str, user_prompt: str) -> SubagentOutput:
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
    data = json.loads(raw_text)
    return SubagentOutput.model_validate(data)
