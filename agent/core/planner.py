import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple
from agent.models.base import BaseModelProvider

class BasePlanner(ABC):
    def __init__(self, model_provider: BaseModelProvider):
        self.model_provider = model_provider

    @abstractmethod
    async def create_plan(self, task: str, observation: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Returns a list of step descriptions and a list of structured tool calls for those steps."""
        pass


class RuleBasedPlanner(BasePlanner):
    async def create_plan(self, task: str, observation: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        # Perform matches case-insensitively on original task to preserve typed text casing
        
        # Rule 1: Launch app AND type text (e.g. "Open Notepad and type Hello SPR Saathi")
        match_launch_type = re.search(
            r"(?:open|launch|start)\s+([a-zA-Z0-9_\-\.]+)\s+and\s+(?:type|write|enter)\s+(.+)",
            task,
            re.IGNORECASE
        )
        if match_launch_type:
            app_raw = match_launch_type.group(1).strip()
            text_val = match_launch_type.group(2).strip()
            
            app_exe = self._resolve_app_executable(app_raw)
            app_title = app_raw.capitalize()
            
            steps_desc = [
                f"Launch application: {app_exe}",
                f"Wait and focus window for: {app_title}",
                f"Type text: '{text_val}'"
            ]
            tool_calls = [
                {
                    "call_id": "step_1",
                    "tool_name": "launch_app",
                    "arguments": {"app_name": app_exe}
                },
                {
                    "call_id": "step_2",
                    "tool_name": "focus_window",
                    "arguments": {"process_name": app_exe, "title_substring": app_raw}
                },
                {
                    "call_id": "step_3",
                    "tool_name": "keyboard_type",
                    "arguments": {"text": text_val}
                }
            ]
            return steps_desc, tool_calls

        # Rule 2: Just launch app (e.g. "Open Notepad")
        match_launch = re.search(r"^(?:open|launch|start)\s+([a-zA-Z0-9_\-\.]+)$", task, re.IGNORECASE)
        if match_launch:
            app_raw = match_launch.group(1).strip()
            app_exe = self._resolve_app_executable(app_raw)
            steps_desc = [f"Launch application: {app_exe}"]
            tool_calls = [
                {
                    "call_id": "step_1",
                    "tool_name": "launch_app",
                    "arguments": {"app_name": app_exe}
                }
            ]
            return steps_desc, tool_calls

        # Rule 3: Just type text (e.g. "type Hello World")
        match_type = re.search(r"^(?:type|write|enter)\s+(.+)$", task, re.IGNORECASE)
        if match_type:
            text_val = match_type.group(1).strip()
            steps_desc = [f"Type text: '{text_val}'"]
            tool_calls = [
                {
                    "call_id": "step_1",
                    "tool_name": "keyboard_type",
                    "arguments": {"text": text_val}
                }
            ]
            return steps_desc, tool_calls

        # Fallback to model completion if no rules match (boundary integration)
        try:
            response = await self.model_provider.generate_with_tools(task, tools=[])
            steps_desc = []
            tool_calls = response.tool_calls or []
            
            if tool_calls:
                for i, tc in enumerate(tool_calls):
                    tc["call_id"] = f"step_{i+1}"
                    steps_desc.append(f"Execute {tc['tool_name']} with arguments: {tc['arguments']}")
            else:
                steps_desc.append("Decomposed task step using mock generator completion")
                tool_calls = [
                    {
                        "call_id": "step_1",
                        "tool_name": "cmd",
                        "arguments": {"command": f"echo Running fallback: {task}"}
                    }
                ]
            return steps_desc, tool_calls
        except Exception:
            return (
                ["Execute echo statement"],
                [{
                    "call_id": "step_1",
                    "tool_name": "cmd",
                    "arguments": {"command": f"echo System received: {task}"}
                }]
            )

    def _resolve_app_executable(self, app_name: str) -> str:
        name = app_name.lower().strip()
        if "notepad" in name:
            return "notepad.exe"
        if "paint" in name or "mspaint" in name:
            return "mspaint.exe"
        if "chrome" in name:
            return "chrome.exe"
        if "calc" in name or "calculator" in name:
            return "calc.exe"
        if not name.endswith(".exe"):
            return f"{name}.exe"
        return name
