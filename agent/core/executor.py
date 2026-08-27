from typing import Dict, Any, Optional
from agent.tools.base import BaseTool
from agent.permissions.broker import PermissionBroker

class ToolExecutor:
    def __init__(self, tools: Dict[str, BaseTool], permission_broker: PermissionBroker):
        self.tools = tools
        self.permission_broker = permission_broker

    async def execute_action(self, tool_name: str, arguments: Dict[str, Any], call_id: str = "") -> Dict[str, Any]:
        # Look up tool
        if tool_name not in self.tools:
            return {
                "call_id": call_id,
                "success": False,
                "output": "",
                "error": f"Tool '{tool_name}' not found."
            }

        tool = self.tools[tool_name]

        # Enforce permission check
        allowed = await self.permission_broker.check_permission(tool_name, tool.category, arguments)
        if not allowed:
            return {
                "call_id": call_id,
                "success": False,
                "output": "",
                "error": f"Permission denied for tool '{tool_name}'."
            }

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
