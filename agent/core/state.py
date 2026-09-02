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
        
        # Bounded Task Model Fields matching Phase 4 Requirements
        self.created_at: Optional[str] = None
        self.updated_at: Optional[str] = None
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.attempt_count = 0
        self.max_attempts = 50

    def reset(self, task: str):
        now_str = datetime.datetime.utcnow().isoformat() + "Z"
        self.status = "queued"
        self.current_task = task
        self.task_id = str(uuid.uuid4())
        self.active_step_id = None
        self.steps = []
        self.takeover_active = False
        self.error_message = None
        self.computer_state = None
        self.action_history = []
        
        self.created_at = now_str
        self.updated_at = now_str
        self.started_at = now_str
        self.completed_at = None
        self.attempt_count = 0

    def update_status(self, status: str):
        self.status = status
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"
        if status in ["completed", "failed", "cancelled", "stopped"]:
            self.completed_at = self.updated_at

    def update_computer_state(self, computer_state: Optional[Dict[str, Any]]):
        self.computer_state = computer_state
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def add_action_history(
        self, 
        action_name: str, 
        parameters: Dict[str, Any], 
        status: str, 
        error_message: Optional[str] = None, 
        duration_ms: int = 0, 
        output: Optional[str] = None,
        obs_before: Optional[Dict[str, Any]] = None,
        obs_after: Optional[Dict[str, Any]] = None
    ):
        clean_params = parameters.copy()
        history_item: Dict[str, Any] = {
            "action": action_name,
            "parameters": clean_params,
            "status": status,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "duration_ms": duration_ms
        }
        if error_message:
            history_item["error"] = error_message
        if output:
            history_item["output"] = output

        # Attach lightweight observation metadata (omitting raw base64 string to keep memory bounded)
        if obs_before:
            history_item["observation_before"] = {
                "active_window": obs_before.get("active_window"),
                "image_available": obs_before.get("image_available", False),
                "image_path": obs_before.get("image_path")
            }
        if obs_after:
            history_item["observation_after"] = {
                "active_window": obs_after.get("active_window"),
                "image_available": obs_after.get("image_available", False),
                "image_path": obs_after.get("image_path")
            }
            
        self.action_history.append(history_item)
        if len(self.action_history) > 50:
            self.action_history = self.action_history[-50:]
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def set_steps(self, steps_descriptions: List[str]):
        self.steps = []
        for i, desc in enumerate(steps_descriptions):
            self.steps.append({
                "step_id": f"step_{i+1}",
                "description": desc,
                "status": "pending",
                "tool_call": None
            })
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    # Plan Mutation Helpers (Requirement 6)
    def set_structured_steps(self, steps: List[Dict[str, Any]]):
        self.steps = steps
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def add_step(self, step: Dict[str, Any], index: Optional[int] = None):
        if "step_id" not in step and "id" in step:
            step["step_id"] = step["id"]
        if "status" not in step:
            step["status"] = "pending"
        if "tool_call" not in step:
            step["tool_call"] = None
            
        if index is None:
            self.steps.append(step)
        else:
            self.steps.insert(index, step)
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def remove_step(self, step_id: str):
        self.steps = [s for s in self.steps if s.get("step_id") != step_id and s.get("id") != step_id]
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def update_step_status(self, step_id: str, status: str):
        for step in self.steps:
            if step.get("step_id") == step_id or step.get("id") == step_id:
                step["status"] = status
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def start_step(self, step_id: str, tool_call: Optional[Dict[str, Any]] = None):
        self.active_step_id = step_id
        for step in self.steps:
            if step.get("step_id") == step_id or step.get("id") == step_id:
                step["status"] = "running"
                step["tool_call"] = tool_call
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def complete_step(self, step_id: str):
        for step in self.steps:
            if step.get("step_id") == step_id or step.get("id") == step_id:
                step["status"] = "completed"
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def fail_step(self, step_id: str):
        for step in self.steps:
            if step.get("step_id") == step_id or step.get("id") == step_id:
                step["status"] = "failed"
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def cancel_all_steps(self):
        for step in self.steps:
            if step["status"] in ["pending", "running"]:
                step["status"] = "cancelled"
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

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
            "action_history": self.action_history,
            
            # Phase 4 fields
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts
        }


