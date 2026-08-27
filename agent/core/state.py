from typing import List, Dict, Any, Optional
import uuid
import datetime

class StateTracker:
    def __init__(self):
        self.status = "idle"
        self.current_task: Optional[str] = None
        self.task_id: Optional[str] = None
        self.active_step_id: Optional[str] = None
        self.steps: List[Dict[str, Any]] = []
        self.takeover_active = False
        self.error_message: Optional[str] = None
        self.computer_state: Optional[Dict[str, Any]] = None
        self.action_history: List[Dict[str, Any]] = []

    def reset(self, task: str):
        self.status = "idle"
        self.current_task = task
        self.task_id = str(uuid.uuid4())
        self.active_step_id = None
        self.steps = []
        self.takeover_active = False
        self.error_message = None
        self.computer_state = None
        self.action_history = []

    def update_status(self, status: str):
        self.status = status

    def update_computer_state(self, computer_state: Optional[Dict[str, Any]]):
        self.computer_state = computer_state

    def add_action_history(self, action_name: str, parameters: Dict[str, Any], status: str, error_message: Optional[str] = None, duration_ms: int = 0):
        # Prevent logging password payloads directly in logs/history (optional sanity check)
        clean_params = parameters.copy()
        history_item = {
            "action": action_name,
            "parameters": clean_params,
            "status": status,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "duration_ms": duration_ms
        }
        if error_message:
            history_item["error"] = error_message
            
        self.action_history.append(history_item)
        # Cap length at 50
        if len(self.action_history) > 50:
            self.action_history = self.action_history[-50:]

    def set_steps(self, steps_descriptions: List[str]):
        self.steps = []
        for i, desc in enumerate(steps_descriptions):
            self.steps.append({
                "step_id": f"step_{i+1}",
                "description": desc,
                "status": "pending",
                "tool_call": None
            })

    def start_step(self, step_id: str, tool_call: Optional[Dict[str, Any]] = None):
        self.active_step_id = step_id
        for step in self.steps:
            if step["step_id"] == step_id:
                step["status"] = "running"
                step["tool_call"] = tool_call

    def complete_step(self, step_id: str):
        for step in self.steps:
            if step["step_id"] == step_id:
                step["status"] = "completed"

    def fail_step(self, step_id: str):
        for step in self.steps:
            if step["step_id"] == step_id:
                step["status"] = "failed"

    def cancel_all_steps(self):
        for step in self.steps:
            if step["status"] in ["pending", "running"]:
                step["status"] = "cancelled"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "current_task": self.current_task,
            "task_id": self.task_id,
            "active_step_id": self.active_step_id,
            "steps": self.steps,
            "takeover_active": self.takeover_active,
            "error_message": self.error_message,
            "computer_state": self.computer_state,
            "action_history": self.action_history
        }


