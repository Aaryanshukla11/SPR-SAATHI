from typing import Dict, Any, Optional
from agent.tools.base import BaseTool
from agent.permissions.broker import PermissionBroker
from agent.control.takeover import TakeoverManager

class ToolExecutor:
    def __init__(self, tools: Dict[str, BaseTool], permission_broker: PermissionBroker, takeover_manager: Optional[TakeoverManager] = None):
        self.tools = tools
        self.permission_broker = permission_broker
        self.takeover_manager = takeover_manager

    async def execute_action(self, tool_name: str, arguments: Dict[str, Any], call_id: str = "") -> Dict[str, Any]:
        # Enforce tool-level input lock during human control
        if self.takeover_manager and self.takeover_manager.is_takeover_active:
            return {
                "call_id": call_id,
                "success": False,
                "output": "",
                "error": "CONTROL_LOCKED"
            }

        # Look up tool
        if tool_name not in self.tools:
            return {
                "call_id": call_id,
                "success": False,
                "output": "",
                "error": f"Tool '{tool_name}' not found."
            }

        tool = self.tools[tool_name]

        # Record active window handle before checking permission (in case prompt steals focus)
        active_hwnd = None
        import ctypes
        from agent.core import win32_utils
        if win32_utils.IS_WINDOWS:
            active_hwnd = ctypes.windll.user32.GetForegroundWindow()

        # Enforce permission check
        allowed = await self.permission_broker.check_permission(tool_name, tool.category, arguments)
        if not allowed:
            return {
                "call_id": call_id,
                "success": False,
                "output": "",
                "error": f"Permission denied for tool '{tool_name}'."
            }

        # Restore window focus if it was a prompt and focus shifted
        policy = self.permission_broker.policy_manager.get_policy(tool_name, tool.category, arguments)
        if policy == "prompt" and active_hwnd and win32_utils.IS_WINDOWS:
            current_hwnd = ctypes.windll.user32.GetForegroundWindow()
            if current_hwnd != active_hwnd:
                win32_utils.focus_window(active_hwnd)
                await asyncio.sleep(0.15)

        # Execute tool
        try:
            result = await tool.execute(arguments)
            result["call_id"] = call_id
            return result
        except Exception as e:
            return {
                "call_id": call_id,
                "success": False,
                "output": "",
                "error": f"Tool execution failed: {str(e)}"
            }
