from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple
from agent.models.base import BaseModelProvider

class BasePlanner(ABC):
    def __init__(self, model_provider: BaseModelProvider):
        self.model_provider = model_provider

    @abstractmethod
    async def create_plan(self, task: str, observation: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Returns a list of step descriptions and a list of structured tool calls for those steps."""
        pass

    def create_high_level_plan(self, task: str) -> List[Dict[str, Any]]:
        """Generates a high-level progress plan representing the goal checklist."""
        pass

    @abstractmethod
    async def revalidate_plan(self, task: str, plan: List[Dict[str, Any]], observation: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
        """Evaluates current plan against desktop state and actions history. Returns completed, replan, valid, or ambiguous."""
        pass


class RuleBasedPlanner(BasePlanner):
    async def revalidate_plan(self, task: str, plan: List[Dict[str, Any]], observation: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
        # Generic revalidation: keep the current plan valid unless empty
        if not plan:
            return "replan"
        return "valid"

    def create_high_level_plan(self, task: str) -> List[Dict[str, Any]]:
        # A simple, generic progress checklist that does not hardcode tool actions
        steps = [
            {"id": "step_1", "description": f"Initialize environment for task: {task}", "status": "pending"},
            {"id": "step_2", "description": "Execute model-driven steps", "status": "pending"},
            {"id": "step_3", "description": "Verify task results", "status": "pending"}
        ]
        for step in steps:
            step["step_id"] = step["id"]
            step["tool_call"] = None
        return steps

    async def create_plan(self, task: str, observation: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        # Generic plan creation returning empty tool calls list
        steps_desc = [f"Decompose task: {task}"]
        tool_calls = []
        return steps_desc, tool_calls
