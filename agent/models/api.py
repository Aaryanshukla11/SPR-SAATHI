from typing import List, Dict, Any, Optional
from .base import BaseModelProvider, ModelResponse

class ApiModelProvider(BaseModelProvider):
    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> ModelResponse:
        return ModelResponse(
            text=f"[API Model '{self.model_name}'] Mock completion for: {prompt[:50]}...",
            raw_response={"provider": "api", "model": self.model_name}
        )

    async def generate_with_tools(self, prompt: str, tools: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> ModelResponse:
        text = f"[API Model '{self.model_name}'] Analyzing request: '{prompt}' and planning steps."
        tool_calls = []

        prompt_lower = prompt.lower()
        if "paint" in prompt_lower:
            tool_calls = [
                {
                    "call_id": "call_paint_1",
                    "tool_name": "launch_app",
                    "arguments": {"app_name": "mspaint.exe"}
                }
            ]
        elif "notepad" in prompt_lower:
            tool_calls = [
                {
                    "call_id": "call_notepad_1",
                    "tool_name": "launch_app",
                    "arguments": {"app_name": "notepad.exe"}
                }
            ]
        elif "chrome" in prompt_lower or "google" in prompt_lower:
            tool_calls = [
                {
                    "call_id": "call_chrome_1",
                    "tool_name": "launch_app",
                    "arguments": {"app_name": "chrome.exe"}
                }
            ]
        else:
            tool_calls = [
                {
                    "call_id": "call_cmd_1",
                    "tool_name": "cmd",
                    "arguments": {"command": "echo Hello from SPR SAATHI"}
                }
            ]

        return ModelResponse(
            text=text,
            tool_calls=tool_calls,
            raw_response={"provider": "api", "model": self.model_name, "mocked": True}
        )
