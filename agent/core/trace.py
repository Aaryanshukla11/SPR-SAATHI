import json
import time
import copy
from typing import Dict, Any, List, Optional

class ExecutionTracer:
    """
    Generic, observational runtime tracer for recording:
    1. Exact model decisions before execution (Step, raw response, parsed decision, tool, args, timestamp).
    2. Exact tool execution events (Tool name, model args, internal coordinate transformation, actual OS coordinates, windows before/after, result).
    3. Context and observation state sent to the model before each decision.

    STRICT PRINCIPLE:
    This class is purely observational. It NEVER modifies, generates, corrects, or replaces actions.
    """
    def __init__(self, task_goal: str = ""):
        self.task_goal = task_goal
        self.start_time = time.time()
        self.steps: List[Dict[str, Any]] = []
        self._current_step: Dict[str, Any] = {}

    def start_step(self, step_number: int, observation: Dict[str, Any], context_summary: Optional[str] = None):
        self._current_step = {
            "step_number": step_number,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "observation_before": copy.deepcopy(observation),
            "context_summary": context_summary,
            "model_decision": {},
            "tool_execution": {}
        }

    def record_model_decision(self, raw_response: Any, parsed_decision: Dict[str, Any]):
        if not self._current_step:
            return
        self._current_step["model_decision"] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "raw_response": str(raw_response),
            "decision_type": parsed_decision.get("decision_type"),
            "tool_name": parsed_decision.get("tool_name"),
            "tool_arguments": copy.deepcopy(parsed_decision.get("arguments", {})),
            "message": parsed_decision.get("message"),
            "question": parsed_decision.get("question"),
            "reason": parsed_decision.get("reason"),
            "duration_seconds": parsed_decision.get("duration_seconds")
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
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
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
        self.steps.append(self._current_step)
        self._current_step = {}

    def get_trace(self) -> Dict[str, Any]:
        return {
            "task_goal": self.task_goal,
            "total_steps": len(self.steps),
            "duration_seconds": round(time.time() - self.start_time, 2),
            "steps": self.steps
        }

    def save_trace(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.get_trace(), f, indent=2)
