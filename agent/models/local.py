import json
import httpx
import re
import urllib.request
from typing import List, Dict, Any, Optional
from .base import BaseModelProvider, ModelResponse

class LocalModelProvider(BaseModelProvider):
    def _get_ollama_model(self) -> str:
        raw_name = (self.model_name or "").strip()
        lower_name = raw_name.lower()
        
        # 1. Fetch tags directly from Ollama
        installed_models: List[str] = []
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2.0) as response:
                data = json.loads(response.read().decode())
                installed_models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            pass
            
        if not installed_models:
            return raw_name or "qwen2.5:latest"

        # 2. Check exact case-insensitive match (e.g. "llama3.2-vision:latest", "qwen2.5:latest")
        for m in installed_models:
            if m.lower() == lower_name:
                return m

        # 3. Check base name match without tag (e.g. "llama3.2-vision" -> "llama3.2-vision:latest")
        for m in installed_models:
            m_base = m.split(":")[0].lower()
            if m_base == lower_name or lower_name.startswith(m_base) or m_base.startswith(lower_name):
                return m

        # 4. Check parameter size / substring match (e.g. "14B" -> "qwen2.5-coder:14B", "7B" -> "qwen2.5-coder:7b")
        for m in installed_models:
            m_low = m.lower()
            if "embed" in m_low:
                continue # skip embedding models for chat
            if lower_name in m_low:
                return m
            # Parameter size hints
            for size_hint in ["32b", "14b", "7b", "3b", "1.5b", "0.5b", "8b", "1b", "70b"]:
                if size_hint in lower_name and size_hint in m_low:
                    return m
            if "vision" in lower_name and ("vision" in m_low or "vl" in m_low or "llava" in m_low):
                return m

        # 5. Default fallback to first non-embedding installed model or raw name
        for m in installed_models:
            if "embed" not in m.lower():
                return m

        return raw_name or installed_models[0]

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

    @property
    def capabilities(self) -> Dict[str, Any]:
        ollama_model = self._get_ollama_model().lower()
        has_vision = any(x in ollama_model for x in ["vision", "llava", "minicpm", "bakllava", "moondream", "qwen-vl", "vl"])
        return {
            "supports_tool_calling": True,
            "supports_structured_output": True,
            "supports_vision": has_vision,
            "supports_streaming": False,
            "context_window": 128000
        }

    async def decide_action(
        self, 
        goal: str, 
        plan: List[Dict[str, Any]], 
        observation: Dict[str, Any], 
        recent_history: List[Dict[str, Any]],
        image_base64: Optional[str] = None
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

        img_b64 = image_base64 if image_base64 is not None else observation.get("image_base64")

        # Multimodal image attachment for vision-capable models
        user_message: Dict[str, Any] = {"role": "user", "content": user_content}
        if self.supports_vision and img_b64:
            user_message["images"] = [img_b64]

        messages = [
            {"role": "system", "content": system_instruction},
            user_message
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
