from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class SkillExecutionResult:
    skill_name: str
    success: bool
    output: Any
    steps_executed: List[str] = field(default_factory=list)
    verification_details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class BaseSkill(ABC):
    """
    Phase 5: Base Skill Specification.
    
    Every skill must define all 8 required attributes per PHASES.md:
    1. name
    2. description
    3. input_schema
    4. output_schema
    5. required_permissions
    6. required_tools
    7. verification_strategy
    8. fallback_strategy
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        pass

    @property
    @abstractmethod
    def output_schema(self) -> Dict[str, Any]:
        pass

    @property
    @abstractmethod
    def required_permissions(self) -> List[str]:
        pass

    @property
    @abstractmethod
    def required_tools(self) -> List[str]:
        pass

    @property
    @abstractmethod
    def verification_strategy(self) -> str:
        pass

    @property
    @abstractmethod
    def fallback_strategy(self) -> str:
        pass

    @abstractmethod
    async def execute(
        self,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> SkillExecutionResult:
        """Executes the high-level reusable workflow."""
        pass
