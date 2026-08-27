import asyncio
import uuid
from typing import Dict, Any, Callable, Optional
from .policies import PolicyManager

class PermissionBroker:
    def __init__(self, policy_manager: PolicyManager):
        self.policy_manager = policy_manager
        # Maps request_id -> asyncio.Future
        self._pending_requests: Dict[str, asyncio.Future] = {}
        # Callback to trigger when user prompt is required
        # Signature: async def callback(request_id: str, tool_name: str, arguments: Dict[str, Any])
        self.on_prompt_callback: Optional[Callable] = None

    async def check_permission(self, tool_name: str, category: str, arguments: Dict[str, Any]) -> bool:
        policy = self.policy_manager.get_policy(tool_name, category)
        
        if policy == "allow":
            return True
        elif policy == "deny":
            return False
        
        # Policy is "prompt", we need user input
        if not self.on_prompt_callback:
            # If no callback registered, fail-safe to Deny
            return False

        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            # Trigger Electron prompt notification
            await self.on_prompt_callback(request_id, tool_name, arguments)
            # Wait for response (decision)
            decision = await future
            return decision == "allow"
        finally:
            self._pending_requests.pop(request_id, None)

    def resolve_permission(self, request_id: str, decision: str):
        if request_id in self._pending_requests:
            future = self._pending_requests[request_id]
            if not future.done():
                future.set_result(decision)
                return True
        return False
