import re
from typing import List, Dict, Any, Optional
from .base import BaseModelProvider, ModelResponse

class ApiModelProvider(BaseModelProvider):
    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> ModelResponse:
        return ModelResponse(
            text=f"[API Model '{self.model_name}'] Mock completion for: {prompt[:50]}...",
            raw_response={"provider": "api", "model": self.model_name}
        )

    async def generate_with_tools(self, prompt: str, tools: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> ModelResponse:
        text = f"[API Model '{self.model_name}'] Analyzing request and planning steps."
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
        else:
            tool_calls = [
                {
                    "call_id": "call_cmd_1",
                    "tool_name": "cmd",
                    "arguments": {"command": "echo System received task"}
                }
            ]

        return ModelResponse(
            text=text,
            tool_calls=tool_calls,
            raw_response={"provider": "api", "model": self.model_name, "mocked": True}
        )

    async def decide_action(
        self, 
        goal: str, 
        plan: List[Dict[str, Any]], 
        observation: Dict[str, Any], 
        recent_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Decision-making logic for multi-step Notepad operations, saves, recovery, and plan progress.
        """
        goal_lower = goal.lower()
        active_win = observation.get("active_window")
        active_process = str(active_win.get("process") or "").lower() if active_win else ""
        active_title = str(active_win.get("title") or "").lower() if active_win else ""

        # Analyze completed actions from the history
        launched = False
        focused = False
        typed = False
        hotkey_saved = False
        filename_typed = False
        saved = False

        for action in recent_history:
            if action.get("status") == "completed":
                name = action.get("action")
                params = action.get("parameters", {})
                if name == "launch_app" and "notepad" in str(params.get("app_name")).lower():
                    launched = True
                elif name == "focus_window" and "notepad" in str(params.get("process_name") or params.get("title_substring")).lower():
                    focused = True
                elif name == "keyboard_type":
                    txt = str(params.get("text", "")).lower()
                    if "hello.txt" in txt or "txt" in txt:
                        filename_typed = True
                    elif "hello" in txt:
                        typed = True
                elif name == "keyboard_hotkey" and any("s" in str(k).lower() for k in params.get("keys", [])):
                    hotkey_saved = True
                elif name == "keyboard_press" and "enter" in str(params.get("key", "")).lower():
                    saved = True
        # Notepad flow
        if "notepad" in goal_lower:
            notepad_running = "notepad.exe" in active_process or "notepad" in active_title
            visible_windows = observation.get("visible_windows", [])
            any_notepad = any("notepad" in str(w.get("process", "")).lower() or "notepad" in str(w.get("title", "")).lower() for w in visible_windows)

            if not notepad_running and not any_notepad:
                return {
                    "decision_type": "tool_call",
                    "tool_name": "launch_app",
                    "arguments": {"app_name": "notepad.exe"}
                }

            if not notepad_running and any_notepad and not focused:
                return {
                    "decision_type": "tool_call",
                    "tool_name": "focus_window",
                    "arguments": {"process_name": "notepad.exe", "title_substring": "Notepad"}
                }

            if "type" in goal_lower or "write" in goal_lower:
                if not typed:
                    match = re.search(r"(?:type|write|enter)\s+(.+?)(?:,|$|and\s+save)", goal, re.IGNORECASE)
                    text_to_type = match.group(1).strip() if match else "Hello SPR Saathi"
                    text_to_type = text_to_type.strip("'\"")
                    return {
                        "decision_type": "tool_call",
                        "tool_name": "keyboard_type",
                        "arguments": {"text": text_to_type}
                    }

            if "save" in goal_lower:
                if not hotkey_saved:
                    return {
                        "decision_type": "tool_call",
                        "tool_name": "keyboard_hotkey",
                        "arguments": {"keys": ["ctrl", "s"]}
                    }
                if not filename_typed:
                    return {
                        "decision_type": "tool_call",
                        "tool_name": "keyboard_type",
                        "arguments": {"text": "hello.txt"}
                    }
                if not saved:
                    return {
                        "decision_type": "tool_call",
                        "tool_name": "keyboard_press",
                        "arguments": {"key": "enter"}
                    }

            return {
                "decision_type": "final",
                "message": "Task completed successfully. Notepad opened, typed, and saved."
            }

        # Default fallback
        return {
            "decision_type": "final",
            "message": f"Goal '{goal}' completed successfully (fallback API simulation)."
        }
