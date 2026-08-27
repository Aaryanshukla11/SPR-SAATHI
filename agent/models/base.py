from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ModelResponse(BaseModel):
    text: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Any = None

class ModelDecision(BaseModel):
    decision_type: str = Field(..., description="Must be 'tool_call', 'final', 'replan', 'ask_user', or 'wait'")
    tool_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    question: Optional[str] = None
    duration_seconds: Optional[float] = None
    reason: Optional[str] = None

def validate_model_decision(decision: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validates model output schemas and values against the Typed Decision Protocol.
    Returns (is_valid, error_message).
    """
    dtype = decision.get("decision_type")
    valid_types = {"tool_call", "final", "replan", "ask_user", "wait"}
    if dtype not in valid_types:
        return False, f"Invalid decision type: '{dtype}'. Must be one of {valid_types}."

    if dtype == "tool_call":
        if not decision.get("tool_name"):
            return False, "Missing 'tool_name' in 'tool_call' decision."
        if decision.get("arguments") is None:
            return False, "Missing 'arguments' in 'tool_call' decision."
            
    elif dtype == "final":
        if not decision.get("message"):
            return False, "Missing 'message' in 'final' decision."
            
    elif dtype == "replan":
        if not decision.get("reason"):
            return False, "Missing 'reason' in 'replan' decision."
            
    elif dtype == "ask_user":
        if not decision.get("question"):
            return False, "Missing 'question' in 'ask_user' decision."
            
    elif dtype == "wait":
        duration = decision.get("duration_seconds")
        if duration is None:
            return False, "Missing 'duration_seconds' in 'wait' decision."
        try:
            val = float(duration)
            if val <= 0:
                return False, "'duration_seconds' must be positive."
        except (ValueError, TypeError):
            return False, "'duration_seconds' must be a valid number."

    return True, None

class BaseModelProvider(ABC):
    def __init__(self, model_name: str, config: Optional[Dict[str, Any]] = None):
        self.model_name = model_name
        self.config = config or {}

    @property
    def capabilities(self) -> Dict[str, Any]:
        """Expose capabilities of the model."""
        return {
            "supports_tool_calling": True,
            "supports_structured_output": True,
            "supports_vision": False,
            "supports_streaming": False,
            "context_window": 128000
        }

    @abstractmethod
    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> ModelResponse:
        """Generates text from a prompt."""
        pass

    @abstractmethod
    async def generate_with_tools(self, prompt: str, tools: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> ModelResponse:
        """Generates completing structured tool calls if requested."""
        pass

    @abstractmethod
    async def decide_action(
        self, 
        goal: str, 
        plan: List[Dict[str, Any]], 
        observation: Dict[str, Any], 
        recent_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Returns a structured next action decision."""
        pass
