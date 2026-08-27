from typing import Dict, Any
from .base import BaseTool

class CmdTool(BaseTool):
    @property
    def name(self) -> str:
        return "cmd"

    @property
    def description(self) -> str:
        return "Execute a command line (cmd.exe) prompt (restricted in Phase 0)."

    @property
    def category(self) -> str:
        return "terminal"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command line string to run"}
            },
            "required": ["command"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        command = arguments.get("command", "")
        # For Phase 0, restrict command execution for security. Allow only 'echo' or show dry-run.
        if command.strip().lower().startswith("echo"):
            msg = f"CMD Output: {command.replace('echo', '', 1).strip()}"
            return {
                "call_id": "",
                "success": True,
                "output": msg,
                "error": None
            }
        else:
            msg = f"[Restricted execution in Phase 0] Dry run of CMD: '{command}'"
            print(msg)
            return {
                "call_id": "",
                "success": True,
                "output": msg,
                "error": None
            }


class PowerShellTool(BaseTool):
    @property
    def name(self) -> str:
        return "powershell"

    @property
    def description(self) -> str:
        return "Execute a PowerShell script block (restricted in Phase 0)."

    @property
    def category(self) -> str:
        return "powershell"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "PowerShell command or script block"}
            },
            "required": ["script"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        script = arguments.get("script", "")
        msg = f"[Restricted execution in Phase 0] Dry run of PowerShell: '{script}'"
        print(msg)
        return {
            "call_id": "",
            "success": True,
            "output": msg,
            "error": None
        }
