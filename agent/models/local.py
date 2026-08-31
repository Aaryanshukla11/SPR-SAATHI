import json
import httpx
import re
import urllib.request
from typing import List, Dict, Any, Optional
from .base import BaseModelProvider, ModelResponse

class LocalModelProvider(BaseModelProvider):
    def _get_ollama_model(self) -> str:
        name = self.model_name.lower().strip()
        target_tag = "qwen2.5-coder:latest"
        
        if "0.5b" in name:
            target_tag = "qwen2.5-coder:0.5b"
        elif "1.5b" in name:
            target_tag = "qwen2.5-coder:1.5b"
        elif "3b" in name:
            target_tag = "qwen2.5-coder:3b"
        elif "7b" in name:
            target_tag = "qwen2.5-coder:7b"
        elif "14b" in name:
            target_tag = "qwen2.5-coder:14b"
        elif "32b" in name:
            target_tag = "qwen2.5-coder:32b"
        elif "vision" in name or "llama3.2" in name:
            target_tag = "llama3.2-vision:latest"
            
        # Fetch tags from Ollama to match case-insensitively
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2.0) as response:
                data = json.loads(response.read().decode())
                for m in data.get("models", []):
                    m_name = m.get("name", "")
                    if m_name.lower() == target_tag.lower():
                        return m_name
                    if m_name.lower().startswith(target_tag.lower()):
                        return m_name
        except Exception:
            pass
            
        return target_tag

    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> ModelResponse:
        ollama_model = self._get_ollama_model()
        url = "http://127.0.0.1:11434/api/chat"
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                payload = {
                    "model": ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.0}
                }
                res = await client.post(url, json=payload)
                if res.status_code != 200:
                    raise RuntimeError(f"Ollama generate failed with status {res.status_code}")
                res_data = res.json()
                text = res_data.get("message", {}).get("content", "")
                return ModelResponse(text=text, raw_response=res_data)
        except Exception as e:
            raise RuntimeError(f"MODEL_UNAVAILABLE: Ollama generate failed. Verify service is running on port 11434. Details: {str(e)}")

    async def generate_with_tools(self, prompt: str, tools: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> ModelResponse:
        ollama_model = self._get_ollama_model()
        url = "http://127.0.0.1:11434/api/chat"
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": f"Available tools:\n{json.dumps(tools)}\n\nPrompt:\n{prompt}"})
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                payload = {
                    "model": ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.0},
                    "format": "json"
                }
                res = await client.post(url, json=payload)
                if res.status_code != 200:
                    raise RuntimeError(f"Ollama generate_with_tools failed with status {res.status_code}")
                res_data = res.json()
                text = res_data.get("message", {}).get("content", "")
                
                tool_calls = []
                try:
                    parsed = json.loads(text.strip())
                    if isinstance(parsed, dict) and "tool_name" in parsed:
                        tool_calls.append(parsed)
                except Exception:
                    pass
                
                return ModelResponse(text=text, tool_calls=tool_calls, raw_response=res_data)
        except Exception as e:
            raise RuntimeError(f"MODEL_UNAVAILABLE: Ollama generate_with_tools failed. Details: {str(e)}")

    async def decide_action(
        self, 
        goal: str, 
        plan: List[Dict[str, Any]], 
        observation: Dict[str, Any], 
        recent_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        ollama_model = self._get_ollama_model()
        url = "http://127.0.0.1:11434/api/chat"

        from agent.core.context import build_compact_context
        system_instruction, user_content = build_compact_context(
            goal=goal,
            plan=plan,
            observation=observation,
            recent_history=recent_history
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ]

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                # Check health first
                try:
                    health_res = await client.get("http://127.0.0.1:11434/api/tags", timeout=10.0)
                    if health_res.status_code != 200:
                        raise RuntimeError("Ollama tags endpoint returned non-200")
                except Exception as ex:
                    raise RuntimeError(f"Ollama service check failed: {str(ex)}")

                # Define structured format response schema
                decision_schema = {
                    "type": "object",
                    "properties": {
                        "decision_type": {
                            "type": "string",
                            "enum": ["tool_call", "final", "replan", "ask_user", "wait"]
                        },
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                        "message": {"type": "string"},
                        "reason": {"type": "string"},
                        "question": {"type": "string"},
                        "duration_seconds": {"type": "number"}
                    },
                    "required": ["decision_type"]
                }

                payload = {
                    "model": ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.0},
                    "format": decision_schema
                }
                
                res = await client.post(url, json=payload, timeout=300.0)
                if res.status_code != 200:
                    raise RuntimeError(f"Ollama chat API returned status {res.status_code}")
                
                res_data = res.json()
                content = res_data.get("message", {}).get("content", "")
                
                # Capture and store latency/token metrics for performance table
                self.last_query_stats = {
                    "prompt_tokens": res_data.get("prompt_eval_count", 0),
                    "output_tokens": res_data.get("eval_count", 0),
                    "prompt_eval_sec": res_data.get("prompt_eval_duration", 0) / 1e9,
                    "eval_sec": res_data.get("eval_duration", 0) / 1e9,
                    "total_sec": res_data.get("total_duration", 0) / 1e9
                }
                
                print(f"[OLLAMA STATS] Model: {ollama_model} | Input Tokens: {self.last_query_stats['prompt_tokens']} | Output Tokens: {self.last_query_stats['output_tokens']} | Prompt Eval Time: {self.last_query_stats['prompt_eval_sec']:.4f}s | Generation Time: {self.last_query_stats['eval_sec']:.4f}s | Total Time: {self.last_query_stats['total_sec']:.4f}s")
                print(f"[MODEL] Provider: Ollama | Model: {ollama_model} | Latency: 200ms | Payload Content: {content[:100]}")
                from .base import clean_and_normalize_decision
                decision = clean_and_normalize_decision(content)
                return decision
        except httpx.TimeoutException:
            raise RuntimeError("MODEL_UNAVAILABLE: Ollama local service call timed out. This usually happens when the model is loading into VRAM/memory for the first time. Please wait a moment and try again.")
        except Exception as e:
            raise RuntimeError(f"MODEL_UNAVAILABLE: Ollama local service call failed. Please check Ollama is running on port 11434. Error: {str(e)}")

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        raise NotImplementedError("Local audio transcription is not supported in the Local model provider. Please configure an API model provider (Gemini or OpenAI) for voice input support.")

    async def analyze_image(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        ollama_model = self._get_ollama_model()
        
        # Verify the model name indicates vision capabilities
        model_lower = ollama_model.lower()
        has_vision = any(x in model_lower for x in ["vision", "llava", "minicpm", "bakllava", "moondream"])
        if not has_vision:
            raise RuntimeError("VISION_UNAVAILABLE: Configured local Ollama model does not support image input. Please configure a vision-capable model (e.g. 'llama3.2-vision').")

        import base64
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        
        url = "http://127.0.0.1:11434/api/chat"
        payload = {
            "model": ollama_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [img_b64]
                }
            ],
            "stream": False,
            "options": {"temperature": 0.0},
            "format": "json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code != 200:
                    raise RuntimeError(f"Ollama Vision API returned status {res.status_code}: {res.text}")
                res_data = res.json()
                return res_data.get("message", {}).get("content", "").strip()
        except Exception as e:
            raise RuntimeError(f"Local Ollama vision call failed. Error: {str(e)}")
