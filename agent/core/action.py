import uuid
import datetime
from enum import Enum
from typing import Dict, Any, Optional

class ActionStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED_SUCCESS = "verified_success"
    VERIFICATION_FAILED = "verification_failed"

class Action:
    """
    Represents an atomic, identifiable action generated and executed by the agent.
    Satisfies Phase 1 Action System specification:
      - Action ID (globally unique)
      - Task ID (parent task)
      - Action Type (tool name or decision type)
      - Arguments (input parameters)
      - Status (pending, executing, completed, failed, cancelled)
      - Timestamp (ISO 8601 UTC)
      - Result (execution output or error payload)
      - Verification Status (unverified, verified_success, verification_failed)
    """
    def __init__(
        self,
        task_id: str,
        action_type: str,
        arguments: Dict[str, Any],
        action_id: Optional[str] = None,
        step_id: Optional[str] = None
    ):
        self.action_id: str = action_id or f"act_{uuid.uuid4().hex[:12]}"
        self.task_id: str = task_id
        self.step_id: Optional[str] = step_id
        self.action_type: str = action_type
        self.arguments: Dict[str, Any] = arguments.copy() if arguments else {}
        self.status: ActionStatus = ActionStatus.PENDING
        self.timestamp: str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.duration_ms: int = 0
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.output: Optional[str] = None
        self.verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
        self.observation_before: Optional[Dict[str, Any]] = None
        self.observation_after: Optional[Dict[str, Any]] = None

    def start_execution(self):
        self.status = ActionStatus.EXECUTING
        self.timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def complete(
        self,
        output: Optional[str] = None,
        result_payload: Optional[Dict[str, Any]] = None,
        duration_ms: int = 0,
        verification_status: VerificationStatus = VerificationStatus.VERIFIED_SUCCESS,
        obs_before: Optional[Dict[str, Any]] = None,
        obs_after: Optional[Dict[str, Any]] = None
    ):
        self.status = ActionStatus.COMPLETED
        self.output = output
        self.result = result_payload or {"output": output}
        self.duration_ms = duration_ms
        self.verification_status = verification_status
        self.observation_before = obs_before
        self.observation_after = obs_after

    def fail(
        self,
        error_message: str,
        result_payload: Optional[Dict[str, Any]] = None,
        duration_ms: int = 0,
        verification_status: VerificationStatus = VerificationStatus.VERIFICATION_FAILED,
        obs_before: Optional[Dict[str, Any]] = None,
        obs_after: Optional[Dict[str, Any]] = None
    ):
        self.status = ActionStatus.FAILED
        self.error = error_message
        self.result = result_payload or {"error": error_message}
        self.duration_ms = duration_ms
        self.verification_status = verification_status
        self.observation_before = obs_before
        self.observation_after = obs_after

    def cancel(self, reason: str = "Task cancelled"):
        self.status = ActionStatus.CANCELLED
        self.error = reason
        self.verification_status = VerificationStatus.UNVERIFIED

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "action_id": self.action_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "action_type": self.action_type,
            "action": self.action_type,  # backward compatibility alias
            "arguments": self.arguments,
            "parameters": self.arguments,  # backward compatibility alias
            "status": self.status.value,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "verification_status": self.verification_status.value
        }
        if self.output is not None:
            data["output"] = self.output
        if self.error is not None:
            data["error"] = self.error
        if self.result is not None:
            data["result"] = self.result
        if self.observation_before:
            data["observation_before"] = {
                "active_window": self.observation_before.get("active_window"),
                "image_available": self.observation_before.get("image_available", False),
                "image_path": self.observation_before.get("image_path")
            }
        if self.observation_after:
            data["observation_after"] = {
                "active_window": self.observation_after.get("active_window"),
                "image_available": self.observation_after.get("image_available", False),
                "image_path": self.observation_after.get("image_path")
            }
        return data
