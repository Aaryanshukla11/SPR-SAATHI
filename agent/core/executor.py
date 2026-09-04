import asyncio
import uuid
from typing import Dict, Any, Optional, Set
from agent.tools.base import BaseTool
from agent.permissions.broker import PermissionBroker
from agent.control.takeover import TakeoverManager

class ToolExecutor:
    def __init__(self, tools: Dict[str, BaseTool], permission_broker: PermissionBroker, takeover_manager: Optional[TakeoverManager] = None):
        self.tools = tools
        self.permission_broker = permission_broker
        self.takeover_manager = takeover_manager
        self._execution_lock = asyncio.Lock()
        self._active_call_ids: Set[str] = set()
        self._completed_call_results: Dict[str, Dict[str, Any]] = {}

    async def execute_action(self, tool_name: str, arguments: Dict[str, Any], call_id: str = "", task_id: str = "") -> Dict[str, Any]:
        effective_id = call_id or f"act_{uuid.uuid4().hex[:12]}"
        cache_key = f"{task_id}:{effective_id}" if task_id else effective_id

        # Idempotency check: if this exact action/call ID has already completed execution, return cached result
        if cache_key in self._completed_call_results:
            cached = dict(self._completed_call_results[cache_key])
            cached["duplicate_dispatch_prevented"] = True
            return cached

        # Enforce action ID idempotency (reject duplicate concurrent execution of same action ID)
        if cache_key in self._active_call_ids:
            return {
                "call_id": effective_id,
                "action_id": effective_id,
                "task_id": task_id,
                "success": False,
                "output": "",
                "error": f"Duplicate concurrent execution rejected for action ID '{effective_id}'."
            }

        # Global async serialization: guarantee only one computer/system action runs at a time
        async with self._execution_lock:
            # Re-check completed call IDs after acquiring lock
            if cache_key in self._completed_call_results:
                cached = dict(self._completed_call_results[cache_key])
                cached["duplicate_dispatch_prevented"] = True
                return cached

            self._active_call_ids.add(cache_key)
            # Pass call_id into arguments for tool-level tracing
            arguments["call_id"] = effective_id
            if task_id:
                arguments["task_id"] = task_id
            try:
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
                    result["call_id"] = effective_id
                    result["action_id"] = effective_id
                    result["task_id"] = task_id
                    if len(self._completed_call_results) > 500:
                        self._completed_call_results.pop(next(iter(self._completed_call_results)))
                    self._completed_call_results[cache_key] = result
                    return result
                except Exception as e:
                    err_res = {
                        "call_id": effective_id,
                        "action_id": effective_id,
                        "task_id": task_id,
                        "success": False,
                        "output": "",
                        "error": f"Tool execution failed: {str(e)}"
                    }
                    if len(self._completed_call_results) > 500:
                        self._completed_call_results.pop(next(iter(self._completed_call_results)))
                    self._completed_call_results[cache_key] = err_res
                    return err_res
            finally:
                self._active_call_ids.discard(cache_key)

    def clear_completed_cache(self, task_id: Optional[str] = None):
        """Clears completed call cache for a specific task or globally."""
        if not task_id:
            self._completed_call_results.clear()
        else:
            prefix = f"{task_id}:"
            to_remove = [k for k in self._completed_call_results if k.startswith(prefix)]
            for k in to_remove:
                self._completed_call_results.pop(k, None)
