import re
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger("agent.core.uncertainty")


class UncertaintyTrigger(str, Enum):
    MULTIPLE_FILES_MATCH = "multiple_files_match"
    AMBIGUOUS_REQUEST = "ambiguous_request"
    MISSING_INFORMATION = "missing_information"
    CONFLICTING_INSTRUCTIONS = "conflicting_instructions"
    DESTRUCTIVE_OPERATION = "destructive_operation"


class UncertaintyDetector:
    """
    Phase 15: Human-in-the-Loop Intelligence & Uncertainty Detection Engine.
    
    Detects when the agent should pause and ask the user rather than guessing:
    1. Multiple files match a user query (e.g. 3 presentation files from last week)
    2. Request is ambiguous or underspecified
    3. Critical parameters are missing
    4. Conflicting directives
    5. Destructive operations (rmdir, permanent file deletion, kill process)
    """

    DESTRUCTIVE_TERMS = {
        "delete", "remove", "erase", "wipe", "format", "destroy",
        "drop", "truncate", "kill", "terminate", "rmdir", "del"
    }

    AMBIGUOUS_TERMS = {
        "stuff", "things", "whatever", "something", "that file",
        "the presentation", "the report", "fix it"
    }

    @staticmethod
    def check_file_ambiguity(matching_files: List[Any], query: str) -> Tuple[bool, Optional[str]]:
        """Checks if multiple candidate files match without a clear single winner."""
        if len(matching_files) > 1:
            names = [getattr(f, "filename", str(f)) for f in matching_files[:4]]
            q = f"Multiple files match '{query}': {', '.join(names)}. Which one would you like me to use?"
            return True, q
        return False, None

    @staticmethod
    def check_destructive_uncertainty(tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Checks if an operation has destructive consequences requiring explicit user confirmation."""
        # Terminal command check
        if tool_name in ("cmd", "powershell"):
            cmd = arguments.get("command", "").lower()
            tokens = set(re.findall(r"\w+", cmd))
            if tokens & UncertaintyDetector.DESTRUCTIVE_TERMS:
                q = f"Executing '{cmd[:80]}' is a potentially destructive operation. Would you like me to proceed?"
                return True, q
        return False, None

    @staticmethod
    def check_instruction_conflict(goal: str) -> Tuple[bool, Optional[str]]:
        """Checks if contradictory instructions are present."""
        g_lower = goal.lower()
        if "delete" in g_lower and "keep" in g_lower:
            return True, "Instructions mention both deleting and keeping files. Please clarify your intention."
        if "overwrite" in g_lower and "preserve" in g_lower:
            return True, "Instructions mention both overwriting and preserving data. Please confirm."
        return False, None

    @staticmethod
    def check_ambiguity(goal: str) -> Tuple[bool, Optional[str]]:
        """Checks if request is overly ambiguous."""
        g_lower = goal.lower().strip()
        if len(g_lower.split()) < 3 and any(t in g_lower for t in ["fix", "do it", "clean", "open"]):
            return True, f"Your request '{goal}' is brief. Could you specify which file or application you'd like me to work with?"
        return False, None


# Global singleton instance
UNCERTAINTY_DETECTOR = UncertaintyDetector()
