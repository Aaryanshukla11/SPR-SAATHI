from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    def __init__(self):
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """The identifier of the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A user-friendly description of what the tool does."""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """The category of this tool (e.g. computer, windows, filesystem)."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON Schema of the arguments this tool accepts."""
        pass

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the tool with arguments and returns a result dict matching ToolResult schema."""
        pass
