from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class ModelResponse(BaseModel):
    text: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Any = None

class BaseModelProvider(ABC):
    def __init__(self, model_name: str, config: Optional[Dict[str, Any]] = None):
        self.model_name = model_name
        self.config = config or {}

    @abstractmethod
    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> ModelResponse:
        """Generates text from a prompt."""
        pass

    @abstractmethod
    async def generate_with_tools(self, prompt: str, tools: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> ModelResponse:
        """Generates completing structured tool calls if requested."""
        pass
