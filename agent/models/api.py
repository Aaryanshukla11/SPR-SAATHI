import json
import httpx
import re
from typing import List, Dict, Any, Optional
from .base import (
    BaseModelProvider, ModelResponse,
    safe_parse_api_json, clean_and_normalize_decision,
    ModelPipelineError, ModelNetworkError, ModelHttpError,
    ModelEmptyResponseError, ModelApiJsonError, ModelInvalidContentError,
    ModelDecisionParseError
)

class ApiModelProvider(BaseModelProvider):
    def _get_api_key(self, provider: str) -> Optional[str]:
        if self.config.get("api_key"):
            return self.config["api_key"]
        
        # Fallback to environment variables
        import os
        if provider == "gemini":
            return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        elif provider == "openai":
            return os.environ.get("OPENAI_API_KEY")
        elif provider == "anthropic":
            return os.environ.get("ANTHROPIC_API_KEY")
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    def _resolve_provider_and_model(self) -> tuple[str, str]:
        name = self.model_name.lower()
        if "gpt" in name or "openai" in name:
            model = "gpt-4o"
            if "mini" in name:
                model = "gpt-4o-mini"
            return "openai", model
        elif "gemini" in name:
            model = "gemini-1.5-flash"
            if "pro" in name:
                model = "gemini-1.5-pro"
            elif "3.7" in name or "2.0" in name:
                model = "gemini-2.0-flash"
            return "gemini", model
        elif "claude" in name or "anthropic" in name or "sonnet" in name or "haiku" in name:
            model = "claude-3-5-sonnet-20241022"
            if "haiku" in name:
                model = "claude-3-5-haiku-20241022"
            return "anthropic", model
    @property
    def capabilities(self) -> Dict[str, Any]:
        return {
            "supports_tool_calling": True,
            "supports_structured_output": True,
            "supports_vision": True,
            "supports_streaming": False,
            "context_window": 128000
        }

    async def _make_api_call(self, system_instruction: str, user_content: str, image_base64: Optional[str] = None, require_json: bool = False) -> str:
        provider, model = self._resolve_provider_and_model()
        api_key = self._get_api_key(provider)
        if not api_key:
            raise RuntimeError("API_CREDENTIALS_MISSING: Cloud API key was not configured.")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                # Format user content with multimodal image if available
                if image_base64:
                    user_msg_content: Any = [
                        {"type": "text", "text": user_content},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}", "detail": "high"}}
                    ]
                else:
                    user_msg_content = user_content

                payload: Dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_msg_content}
                    ],
                    "temperature": 0.0
                }
                if require_json:
                    payload["response_format"] = {"type": "json_object"}

                res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise RuntimeError(f"OpenAI API call failed with status {res.status_code}: {res.text}")
                res_data = safe_parse_api_json(res.text, endpoint=url, status_code=res.status_code)
                choices = res_data.get("choices", [])
                if not choices:
                    raise ModelInvalidContentError(f"OpenAI response missing 'choices': {res.text[:100]}")
                return choices[0].get("message", {}).get("content", "") or ""
                
            elif provider == "gemini":
                # Maps gemini models to beta API endpoints
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                
                parts: List[Dict[str, Any]] = [{"text": user_content}]
                if image_base64:
                    parts.append({
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": image_base64
                        }
                    })

                gen_config: Dict[str, Any] = {"temperature": 0.0}
                if require_json:
                    gen_config["responseMimeType"] = "application/json"

                payload = {
                    "contents": [
                        {"role": "user", "parts": parts}
                    ],
                    "systemInstruction": {
                        "parts": [{"text": system_instruction}]
                    },
                    "generationConfig": gen_config
                }
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise RuntimeError(f"Gemini API call failed with status {res.status_code}: {res.text}")
                res_data = safe_parse_api_json(res.text, endpoint=url, status_code=res.status_code)
                candidates = res_data.get("candidates", [])
                if not candidates:
                    feedback = res_data.get("promptFeedback", {})
                    raise ModelInvalidContentError(f"Gemini response has no candidates (feedback: {feedback}): {res.text[:100]}")
                c_parts = candidates[0].get("content", {}).get("parts", [])
                if not c_parts:
                    raise ModelInvalidContentError(f"Gemini candidate content has no parts: {res.text[:100]}")
                return c_parts[0].get("text", "") or ""
                
            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                
                if image_base64:
                    user_msg_content = [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64
                            }
                        },
                        {"type": "text", "text": user_content}
                    ]
                else:
                    user_msg_content = user_content

                payload = {
                    "model": model,
                    "max_tokens": 4096,
                    "system": system_instruction,
                    "messages": [
                        {"role": "user", "content": user_msg_content}
                    ],
                    "temperature": 0.0
                }
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise RuntimeError(f"Anthropic API call failed with status {res.status_code}: {res.text}")
                res_data = safe_parse_api_json(res.text, endpoint=url, status_code=res.status_code)
                c_list = res_data.get("content", [])
                if not c_list:
                    raise ModelInvalidContentError(f"Anthropic response has no content blocks: {res.text[:100]}")
                return c_list[0].get("text", "") or ""
                
            else:
                raise ValueError(f"Unknown API provider: {provider}")

    async def generate(self, prompt: str, system_instruction: Optional[str] = None, image_base64: Optional[str] = None) -> ModelResponse:
        system = system_instruction or "You are a helpful assistant."
        try:
            content = await self._make_api_call(system, prompt, image_base64=image_base64, require_json=False)
            return ModelResponse(text=content, raw_response={"provider_model": self.model_name})
        except Exception as e:
            err_str = str(e)
            if "API_CREDENTIALS_MISSING" in err_str:
                raise RuntimeError("API_CREDENTIALS_MISSING")
            raise RuntimeError(f"API generate call failed. Details: {err_str}")

    async def generate_with_tools(self, prompt: str, tools: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> ModelResponse:
        system = system_instruction or "You are a helpful assistant."
        user = f"Available tools:\n{json.dumps(tools)}\n\nPrompt:\n{prompt}"
        try:
            content = await self._make_api_call(system, user, require_json=True)
            tool_calls = []
            try:
                parsed = json.loads(content.strip())
                if isinstance(parsed, dict) and "tool_name" in parsed:
                    tool_calls.append(parsed)
            except Exception:
                pass
            return ModelResponse(text=content, tool_calls=tool_calls, raw_response={"provider_model": self.model_name})
        except Exception as e:
            err_str = str(e)
            if "API_CREDENTIALS_MISSING" in err_str:
                raise RuntimeError("API_CREDENTIALS_MISSING")
            raise RuntimeError(f"API generate_with_tools call failed. Details: {err_str}")

    async def decide_action(
        self, 
        goal: str, 
        plan: List[Dict[str, Any]], 
        observation: Dict[str, Any], 
        recent_history: List[Dict[str, Any]],
        image_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        from agent.core.context import build_compact_context
        system_instruction, user_content = build_compact_context(
            goal=goal,
            plan=plan,
            observation=observation,
            recent_history=recent_history
        )

        img_b64 = image_base64 if image_base64 is not None else observation.get("image_base64")

        # Layer 1: Call API with structured output enforcement
        try:
            content = await self._make_api_call(system_instruction, user_content, image_base64=img_b64, require_json=True)
        except Exception as e:
            err_str = str(e)
            if "API_CREDENTIALS_MISSING" in err_str:
                raise RuntimeError("API_CREDENTIALS_MISSING")
            raise RuntimeError(f"API local service call failed. Error: {err_str}")

        # Layer 2: Model Decision Parsing & Normalization
        try:
            from .base import clean_and_normalize_decision
            decision = clean_and_normalize_decision(content)
            return decision
        except Exception as e:
            raise RuntimeError(f"Model decision parsing failed: {str(e)}")

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        provider, model = self._resolve_provider_and_model()
        
        # Determine transcribing provider (fallback to gemini or openai if needed)
        transcribe_provider = provider
        api_key = self._get_api_key(provider)
        
        if transcribe_provider not in ["gemini", "openai"]:
            import os
            if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
                transcribe_provider = "gemini"
                api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            elif os.environ.get("OPENAI_API_KEY"):
                transcribe_provider = "openai"
                api_key = os.environ.get("OPENAI_API_KEY")
            else:
                raise RuntimeError("API_CREDENTIALS_MISSING: Gemini or OpenAI API key is required for audio transcription.")
        
        if not api_key:
            raise RuntimeError("API_CREDENTIALS_MISSING: Cloud API key not found for audio transcription.")
            
        async with httpx.AsyncClient(timeout=60.0) as client:
            if transcribe_provider == "openai":
                url = "https://api.openai.com/v1/audio/transcriptions"
                headers = {
                    "Authorization": f"Bearer {api_key}"
                }
                files = {
                    "file": ("audio.webm", audio_bytes, mime_type)
                }
                data = {
                    "model": "whisper-1"
                }
                res = await client.post(url, headers=headers, files=files, data=data)
                if res.status_code != 200:
                    raise RuntimeError(f"OpenAI Whisper API call failed with status {res.status_code}: {res.text}")
                return res.json().get("text", "")
                
            elif transcribe_provider == "gemini":
                # Calls Gemini generateContent with inline base64 audio
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                import base64
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": mime_type,
                                        "data": audio_b64
                                    }
                                },
                                {
                                    "text": "Please provide an accurate transcription of this spoken audio. Output only the transcribed text, nothing else. Do not include any meta comments."
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.0
                    }
                }
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise RuntimeError(f"Gemini transcription call failed with status {res.status_code}: {res.text}")
                res_data = res.json()
                text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip()
            else:
                raise ValueError(f"Unsupported transcription provider: {transcribe_provider}")

    async def analyze_image(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        # Cloud API image analysis implementation
        provider, model = self._resolve_provider_and_model()
        api_key = self._get_api_key(provider)
        if not api_key:
            raise RuntimeError("API_CREDENTIALS_MISSING")
        import base64
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{img_b64}"}}
                            ]
                        }
                    ],
                    "temperature": 0.0
                }
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise RuntimeError(f"OpenAI Vision API returned status {res.status_code}: {res.text}")
                res_data = res.json()
                return res_data["choices"][0]["message"]["content"]
                
            elif provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt},
                                {"inlineData": {"mimeType": mime_type, "data": img_b64}}
                            ]
                        }
                    ],
                    "generationConfig": {"temperature": 0.0}
                }
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise RuntimeError(f"Gemini Vision API returned status {res.status_code}: {res.text}")
                res_data = res.json()
                return res_data["candidates"][0]["content"]["parts"][0]["text"]
                
            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": model,
                    "max_tokens": 4096,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": img_b64
                                    }
                                },
                                {"type": "text", "text": prompt}
                            ]
                        }
                    ],
                    "temperature": 0.0
                }
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    raise RuntimeError(f"Anthropic Vision API returned status {res.status_code}: {res.text}")
                res_data = res.json()
                return res_data["content"][0]["text"]
            else:
                raise ValueError(f"Unknown API provider: {provider}")
