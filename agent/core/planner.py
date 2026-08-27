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

    def create_high_level_plan(self, task: str) -> List[Dict[str, Any]]:
        """Generates a high-level progress plan representing the goal checklist."""
        pass


class RuleBasedPlanner(BasePlanner):
    def create_high_level_plan(self, task: str) -> List[Dict[str, Any]]:
        task_lower = task.lower().strip()
        steps = []
        if "paint" in task_lower:
            steps = [
                {"id": "step_1", "description": "Launch Paint", "status": "pending"},
                {"id": "step_2", "description": "Wait and focus window for Paint", "status": "pending"},
                {"id": "step_3", "description": "Draw walls, roof, and door", "status": "pending"},
                {"id": "step_4", "description": "Verify drawing complete", "status": "pending"}
            ]
        elif "notepad" in task_lower:
            steps = [
                {"id": "step_1", "description": "Launch Notepad", "status": "pending"},
                {"id": "step_2", "description": "Focus Notepad window", "status": "pending"}
            ]
            if "type" in task_lower or "write" in task_lower:
                steps.append({"id": "step_3", "description": "Type the requested text", "status": "pending"})
            if "save" in task_lower:
                steps.append({"id": "step_4", "description": "Save file as hello.txt on Desktop", "status": "pending"})
            steps.append({"id": "step_5", "description": "Verify file saved successfully", "status": "pending"})
        else:
            steps = [
                {"id": "step_1", "description": f"Decompose task: {task}", "status": "pending"}
            ]
        
        # Ensure all steps have step_id
        for step in steps:
            if "step_id" not in step:
                step["step_id"] = step["id"]
        return steps

    async def create_plan(self, task: str, observation: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        task_lower = task.lower().strip()
        
        # Rule 1: Paint drawing workflow
        if "paint" in task_lower and "draw" in task_lower and "house" in task_lower:
            steps_desc = [
                "Launch application: mspaint.exe",
                "Wait and focus window for: Paint",
                "Draw wall (top edge)",
                "Draw wall (right edge)",
                "Draw wall (bottom edge)",
                "Draw wall (left edge)",
                "Draw roof (left slope)",
                "Draw roof (right slope)",
                "Draw door (left edge)",
                "Draw door (top edge)",
                "Draw door (right edge)"
            ]
            tool_calls = [
                {
                    "call_id": "step_1",
                    "tool_name": "launch_app",
                    "arguments": {"app_name": "mspaint.exe"}
                },
                {
                    "call_id": "step_2",
                    "tool_name": "focus_window",
                    "arguments": {"process_name": "mspaint.exe", "title_substring": "Paint"}
                },
                # Wall
                {
                    "call_id": "step_3",
                    "tool_name": "mouse_drag",
                    "arguments": {"start_x": 300, "start_y": 300, "end_x": 500, "end_y": 300, "duration_ms": 300, "target_window": "Paint"}
                },
                {
                    "call_id": "step_4",
                    "tool_name": "mouse_drag",
                    "arguments": {"start_x": 500, "start_y": 300, "end_x": 500, "end_y": 500, "duration_ms": 300, "target_window": "Paint"}
                },
                {
                    "call_id": "step_5",
                    "tool_name": "mouse_drag",
                    "arguments": {"start_x": 500, "start_y": 500, "end_x": 300, "end_y": 500, "duration_ms": 300, "target_window": "Paint"}
                },
                {
                    "call_id": "step_6",
                    "tool_name": "mouse_drag",
                    "arguments": {"start_x": 300, "start_y": 500, "end_x": 300, "end_y": 300, "duration_ms": 300, "target_window": "Paint"}
                },
                # Roof
                {
                    "call_id": "step_7",
                    "tool_name": "mouse_drag",
                    "arguments": {"start_x": 300, "start_y": 300, "end_x": 400, "end_y": 200, "duration_ms": 300, "target_window": "Paint"}
                },
                {
                    "call_id": "step_8",
                    "tool_name": "mouse_drag",
                    "arguments": {"start_x": 400, "start_y": 200, "end_x": 500, "end_y": 300, "duration_ms": 300, "target_window": "Paint"}
                },
                # Door
                {
                    "call_id": "step_9",
                    "tool_name": "mouse_drag",
                    "arguments": {"start_x": 370, "start_y": 500, "end_x": 370, "end_y": 400, "duration_ms": 200, "target_window": "Paint"}
                },
                {
                    "call_id": "step_10",
                    "tool_name": "mouse_drag",
                    "arguments": {"start_x": 370, "start_y": 400, "end_x": 430, "end_y": 400, "duration_ms": 200, "target_window": "Paint"}
                },
                {
                    "call_id": "step_11",
                    "tool_name": "mouse_drag",
                    "arguments": {"start_x": 430, "start_y": 400, "end_x": 430, "end_y": 500, "duration_ms": 200, "target_window": "Paint"}
                }
            ]
            return steps_desc, tool_calls

        # Rule 2: Launch app AND type text (e.g. "Open Notepad and type Hello SPR Saathi")
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

        # Rule 3: Just launch app (e.g. "Open Notepad")
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

        # Rule 4: Just type text (e.g. "type Hello World")
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

        # Fallback to model completion if no rules match
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
