import asyncio
import uuid
import datetime
from typing import Dict, Any, Callable, Optional, List
from .policies import PolicyManager

class PermissionBroker:
    def __init__(self, policy_manager: PolicyManager, state_tracker: Optional[Any] = None):
        self.policy_manager = policy_manager
        self.state_tracker = state_tracker
        # Maps request_id -> asyncio.Future
        self._pending_requests: Dict[str, asyncio.Future] = {}
        # Callback to trigger when user prompt is required
        self.on_prompt_callback: Optional[Callable] = None
        # Default request timeout (in seconds)
        self.timeout_seconds = 60.0
        # Audit trail list capped at 500 entries
        self.audit_trail: List[Dict[str, Any]] = []

    async def check_permission(self, tool_name: str, category: str, arguments: Dict[str, Any]) -> bool:
        policy = self.policy_manager.get_policy(tool_name, category, arguments)
        task_id = self.state_tracker.task_id if self.state_tracker else "unknown_task"
        request_id = str(uuid.uuid4())
        
        if policy == "allow":
            self.log_audit(task_id, request_id, category, tool_name, "execute", "allow", "system")
            return True
        elif policy == "deny":
            self.log_audit(task_id, request_id, category, tool_name, "execute", "deny", "system")
            return False
            
        # Policy is "prompt", we need user input
        if not self.on_prompt_callback:
            # If no callback registered, fail-safe to Deny
            self.log_audit(task_id, request_id, category, tool_name, "execute", "deny", "no_callback")
            return False

        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            # Trigger Electron prompt callback notification
            await self.on_prompt_callback(request_id, tool_name, arguments)
            
            # Wait for response with timeout
            decision = await asyncio.wait_for(future, timeout=self.timeout_seconds)
            allowed = decision == "allow"
            self.log_audit(task_id, request_id, category, tool_name, "execute", decision, "user")
            return allowed
        except asyncio.TimeoutError:
            self.resolve_permission(request_id, "deny")
            self.log_audit(task_id, request_id, category, tool_name, "execute", "timeout_deny", "timeout")
            return False
        except asyncio.CancelledError:
            self.resolve_permission(request_id, "deny")
            self.log_audit(task_id, request_id, category, tool_name, "execute", "cancelled_deny", "cancellation")
            raise
        finally:
            self._pending_requests.pop(request_id, None)

    def resolve_permission(self, request_id: str, decision: str):
        if request_id in self._pending_requests:
            future = self._pending_requests[request_id]
            if not future.done():
                future.set_result(decision)
                return True
        return False

    def cancel_all_pending(self):
        for request_id, future in list(self._pending_requests.items()):
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

    def log_audit(self, task_id: str, request_id: str, scope: str, resource: str, action: str, decision: str, source: str):
        log_item = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "task_id": task_id,
            "request_id": request_id,
            "scope": scope,
            "resource": resource,
            "action": action,
            "decision": decision,
            "source": source
        }
        self.audit_trail.append(log_item)
        if len(self.audit_trail) > 500:
            self.audit_trail = self.audit_trail[-500:]
