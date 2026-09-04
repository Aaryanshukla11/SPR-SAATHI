import uuid
import datetime
from typing import Dict, Any, Optional, List
from agent.core.action import Action

class Task:
    """
    Represents an autonomous goal-driven task managed by SPR SAATHI.
    Maintains full lifecycle state, plan checklist, action history, and verification records.
    """
    def __init__(self, goal: str, task_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.task_id: str = task_id or str(uuid.uuid4())
        self.goal: str = goal
        self.status: str = "created"  # created, planning, running, waiting_permission, acting, verifying, paused, waiting_user, completed, failed, cancelled
        self.created_at: str = now_str
        self.updated_at: str = now_str
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.steps: List[Dict[str, Any]] = []
        self.active_step_id: Optional[str] = None
        self.actions: List[Action] = []
        self.artifacts: List[Dict[str, Any]] = []
        self.error_message: Optional[str] = None
        self.recovery_attempts: int = 0
        self.metadata: Dict[str, Any] = metadata or {}

    def update_status(self, status: str, error_message: Optional[str] = None):
        self.status = status
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.updated_at = now_str
        if status in ["running", "planning", "executing"] and not self.started_at:
            self.started_at = now_str
        if status in ["completed", "failed", "cancelled"]:
            self.completed_at = now_str
        if error_message:
            self.error_message = error_message

    def add_action(self, action: Action):
        self.actions.append(action)
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def set_steps(self, steps: List[Dict[str, Any]]):
        self.steps = steps
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def update_step_status(self, step_id: str, status: str, tool_call: Optional[Dict[str, Any]] = None):
        for s in self.steps:
            if s.get("step_id") == step_id or s.get("id") == step_id:
                s["status"] = status
                if tool_call is not None:
                    s["tool_call"] = tool_call
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def cancel_all_steps(self):
        for s in self.steps:
            if s.get("status") in ["pending", "running"]:
                s["status"] = "cancelled"
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "steps": self.steps,
            "active_step_id": self.active_step_id,
            "action_count": len(self.actions),
            "actions": [a.to_dict() for a in self.actions],
            "artifacts": self.artifacts,
            "error_message": self.error_message,
            "recovery_attempts": self.recovery_attempts,
            "metadata": self.metadata
        }


class TaskManager:
    """
    Dedicated Task Manager responsible for managing the lifecycle of every task.
    Satisfies Phase 1 & Architecture specifications:
      - Unique stable task IDs.
      - Creation timestamps and status tracking.
      - Safe cancellation and pausing.
      - Task registry retaining historical task contexts.
      - Single-active-task ownership enforcement.
    """
    def __init__(self, state_tracker: Optional[Any] = None):
        self.state_tracker = state_tracker
        self.tasks: Dict[str, Task] = {}
        self.active_task_id: Optional[str] = None

    def create_task(self, goal: str, metadata: Optional[Dict[str, Any]] = None) -> Task:
        """
        Creates and registers a new task.
        Guarantees unique UUID task identity.
        """
        active_task = self.get_active_task()
        if active_task and active_task.status in ["running", "planning", "acting", "verifying", "waiting_permission"]:
            raise RuntimeError(f"Cannot create new task: active task '{active_task.task_id}' is currently running.")

        task = Task(goal=goal, metadata=metadata)
        self.tasks[task.task_id] = task
        self.active_task_id = task.task_id

        # Synchronize with StateTracker
        if self.state_tracker:
            self.state_tracker.reset(goal)
            self.state_tracker.task_id = task.task_id
            self.state_tracker.created_at = task.created_at

        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def get_active_task(self) -> Optional[Task]:
        if self.active_task_id and self.active_task_id in self.tasks:
            return self.tasks[self.active_task_id]
        return None

    def list_tasks(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self.tasks.values()]

    def update_task_status(self, task_id: str, status: str, error_message: Optional[str] = None):
        task = self.get_task(task_id)
        if task:
            task.update_status(status, error_message)
            if self.state_tracker and self.active_task_id == task_id:
                self.state_tracker.update_status(status)
                if error_message:
                    self.state_tracker.error_message = error_message

    def cancel_task(self, task_id: Optional[str] = None):
        tid = task_id or self.active_task_id
        if tid and tid in self.tasks:
            task = self.tasks[tid]
            task.update_status("cancelled")
            task.cancel_all_steps()
            for action in task.actions:
                if action.status in ["pending", "executing"]:
                    action.cancel("Task cancelled")
            if self.state_tracker and self.active_task_id == tid:
                self.state_tracker.update_status("cancelled")
                self.state_tracker.cancel_all_steps()

    def pause_task(self, task_id: Optional[str] = None):
        tid = task_id or self.active_task_id
        if tid and tid in self.tasks:
            task = self.tasks[tid]
            task.update_status("paused")
            if self.state_tracker and self.active_task_id == tid:
                self.state_tracker.update_status("paused")

    def resume_task(self, task_id: Optional[str] = None):
        tid = task_id or self.active_task_id
        if tid and tid in self.tasks:
            task = self.tasks[tid]
            task.update_status("running")
            if self.state_tracker and self.active_task_id == tid:
                self.state_tracker.update_status("running")
