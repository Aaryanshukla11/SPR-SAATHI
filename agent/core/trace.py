import json
import time
import copy
import uuid
import datetime
from typing import Dict, Any, List, Optional


class ExecutionTracer:
    """
    Phase 17: Observability and Diagnostics Engine.
    
    Tracks full execution lifecycle with correlation IDs:
    - Task IDs & Action IDs
    - Model decisions (prompt tokens/latency, raw response, parsed decision)
    - Tool calls & arguments
    - Environment observations before and after
    - Multi-level verification results
    - Failure classifications & recovery attempts
    - Errors & performance metrics (durations in ms)
    """

    def __init__(self, task_goal: str = "", task_id: Optional[str] = None):
        self.task_goal = task_goal
        self.task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        self.start_time = time.time()
        self.steps: List[Dict[str, Any]] = []
        self._current_step: Dict[str, Any] = {}

    def start_step(
        self,
        step_number: int,
        observation: Dict[str, Any],
        context_summary: Optional[str] = None,
        action_id: Optional[str] = None
    ):
        act_id = action_id or f"act_{uuid.uuid4().hex[:10]}"
        self._current_step = {
            "task_id": self.task_id,
            "action_id": act_id,
            "step_number": step_number,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "observation_before": copy.deepcopy(observation),
            "context_summary": context_summary,
            "model_decision": {},
            "tool_execution": {},
            "verification": {},
            "recovery": {}
        }

    def record_model_decision(self, raw_response: Any, parsed_decision: Dict[str, Any], latency_ms: int = 0):
        if not self._current_step:
            return
        self._current_step["model_decision"] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "raw_response": str(raw_response),
            "decision_type": parsed_decision.get("decision_type"),
            "tool_name": parsed_decision.get("tool_name"),
            "tool_arguments": copy.deepcopy(parsed_decision.get("arguments", {})),
            "message": parsed_decision.get("message"),
            "question": parsed_decision.get("question"),
            "reason": parsed_decision.get("reason"),
            "latency_ms": latency_ms
        }

    def record_tool_execution(
        self,
        tool_name: str,
        received_arguments: Dict[str, Any],
        transformed_coordinates: Optional[Dict[str, Any]],
        active_window_before: Optional[Dict[str, Any]],
        active_window_after: Optional[Dict[str, Any]],
        result: Dict[str, Any],
        duration_ms: int = 0
    ):
        if not self._current_step:
            return

        self._current_step["tool_execution"] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tool_name": tool_name,
            "arguments_received": copy.deepcopy(received_arguments),
            "coordinate_transformation": copy.deepcopy(transformed_coordinates) if transformed_coordinates else None,
            "active_window_before": copy.deepcopy(active_window_before),
            "active_window_after": copy.deepcopy(active_window_after),
            "success": result.get("success", False),
            "output": result.get("output", ""),
            "error": result.get("error"),
            "duration_ms": duration_ms
        }

    def record_verification(self, status: str, details: Optional[Dict[str, Any]] = None):
        if not self._current_step:
            return
        self._current_step["verification"] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": status,
            "details": details or {}
        }

    def record_recovery_attempt(self, failure_type: str, strategy: str, reason: str):
        if not self._current_step:
            return
        self._current_step["recovery"] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "failure_type": failure_type,
            "strategy": strategy,
            "reason": reason
        }

    def finalize_step(self):
        if self._current_step:
            self.steps.append(self._current_step)
            self._current_step = {}

    def get_trace(self) -> Dict[str, Any]:
        total_duration = round(time.time() - self.start_time, 2)
        return {
            "task_id": self.task_id,
            "task_goal": self.task_goal,
            "total_steps": len(self.steps),
            "duration_seconds": total_duration,
            "steps": self.steps
        }

    def export_diagnostic_summary(self) -> Dict[str, Any]:
        """Generates a concise health and diagnostic summary for troubleshooting."""
        trace = self.get_trace()
        total_steps = len(self.steps)
        failed_steps = [s for s in self.steps if s.get("tool_execution", {}).get("success") is False]
        total_tool_duration_ms = sum(s.get("tool_execution", {}).get("duration_ms", 0) for s in self.steps)

        return {
            "task_id": self.task_id,
            "total_steps": total_steps,
            "failed_steps_count": len(failed_steps),
            "duration_seconds": trace["duration_seconds"],
            "total_tool_duration_ms": total_tool_duration_ms,
            "failures": [
                {
                    "action_id": s.get("action_id"),
                    "tool": s.get("tool_execution", {}).get("tool_name"),
                    "error": s.get("tool_execution", {}).get("error"),
                    "recovery": s.get("recovery")
                }
                for s in failed_steps
            ]
        }

    def save_trace(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.get_trace(), f, indent=2)
