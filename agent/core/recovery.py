from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

from agent.core.verification import VerificationResult, VerificationLevel

logger = logging.getLogger("agent.core.recovery")


class FailureType(str, Enum):
    TOOL_FAILURE = "tool_failure"
    APPLICATION_FAILURE = "application_failure"
    PERMISSION_FAILURE = "permission_failure"
    MODEL_FAILURE = "model_failure"
    FILE_FAILURE = "file_failure"
    NETWORK_FAILURE = "network_failure"
    VERIFICATION_FAILURE = "verification_failure"
    TIMEOUT = "timeout"


class RecoveryAction(str, Enum):
    OBSERVE_AGAIN = "observe_again"
    RETRY_SAFELY = "retry_safely"
    ALTERNATIVE_TOOL = "alternative_tool"
    ALTERNATIVE_SKILL = "alternative_skill"
    REPLAN = "replan"
    ASK_USER = "ask_user"
    STOP = "stop"


@dataclass
class FailureClassification:
    failure_type: FailureType
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


class FailureClassifier:
    """Classifies execution and verification anomalies into Phase 4 taxonomy."""

    @staticmethod
    def classify(
        action_name: str,
        tool_result: Dict[str, Any],
        verification_results: Optional[Dict[VerificationLevel, VerificationResult]] = None,
        exception: Optional[Exception] = None
    ) -> Optional[FailureClassification]:
        verification_results = verification_results or {}
        # 1. Check for exceptions
        if exception:
            err_msg = str(exception).lower()
            if "permission" in err_msg or "denied" in err_msg or "unauthorized" in err_msg:
                return FailureClassification(FailureType.PERMISSION_FAILURE, f"Permission error: {exception}")
            if "timeout" in err_msg or "timed out" in err_msg:
                return FailureClassification(FailureType.TIMEOUT, f"Operation timed out: {exception}")
            if "connection" in err_msg or "network" in err_msg or "dns" in err_msg:
                return FailureClassification(FailureType.NETWORK_FAILURE, f"Network communication error: {exception}")
            return FailureClassification(FailureType.TOOL_FAILURE, f"Execution exception: {exception}")

        # 2. Check for Permission rejection in tool result
        if tool_result.get("permission_denied") or "permission denied" in str(tool_result.get("error", "")).lower():
            return FailureClassification(FailureType.PERMISSION_FAILURE, tool_result.get("error", "Permission rejected"))

        # 3. Check for File verification failures
        if VerificationLevel.FILE in verification_results and not verification_results[VerificationLevel.FILE].passed:
            return FailureClassification(
                FailureType.FILE_FAILURE,
                verification_results[VerificationLevel.FILE].details,
                details=verification_results[VerificationLevel.FILE].metrics
            )

        # 4. Check for Application verification failures
        if VerificationLevel.APPLICATION in verification_results and not verification_results[VerificationLevel.APPLICATION].passed:
            return FailureClassification(
                FailureType.APPLICATION_FAILURE,
                verification_results[VerificationLevel.APPLICATION].details,
                details=verification_results[VerificationLevel.APPLICATION].metrics
            )

        # 5. Check for Tool verification failures
        if VerificationLevel.TOOL in verification_results and not verification_results[VerificationLevel.TOOL].passed:
            return FailureClassification(
                FailureType.TOOL_FAILURE,
                verification_results[VerificationLevel.TOOL].details
            )

        # 6. Check for Visual / Data verification failures
        for vlevel in [VerificationLevel.VISUAL, VerificationLevel.DATA]:
            if vlevel in verification_results and not verification_results[vlevel].passed:
                return FailureClassification(
                    FailureType.VERIFICATION_FAILURE,
                    verification_results[vlevel].details,
                    details=verification_results[vlevel].metrics
                )

        # 7. Fallback: inspect tool_result error string directly
        if tool_result.get("success") is False or tool_result.get("error"):
            err_text = str(tool_result.get("error", "")).lower()
            if "file" in err_text or "not found" in err_text or "no such file" in err_text:
                return FailureClassification(FailureType.FILE_FAILURE, tool_result.get("error", "File error"))
            if "timeout" in err_text or "timed out" in err_text:
                return FailureClassification(FailureType.TIMEOUT, tool_result.get("error", "Timeout"))
            if "network" in err_text or "connection" in err_text:
                return FailureClassification(FailureType.NETWORK_FAILURE, tool_result.get("error", "Network error"))
            if "app" in action_name or "window" in action_name:
                return FailureClassification(FailureType.APPLICATION_FAILURE, tool_result.get("error", "Application failure"))
            return FailureClassification(FailureType.TOOL_FAILURE, tool_result.get("error", "Tool failure"))

        return None


class RecoveryStrategyEngine:
    """
    Implements Phase 4 Graduated Recovery Pipeline:
        Observe Again
            ↓
        Retry Safely
            ↓
        Alternative Tool
            ↓
        Alternative Skill
            ↓
        Replan
            ↓
        Ask User
            ↓
        Stop
        
    Enforces strict recovery limits to prevent infinite retry loops.
    """

    def __init__(
        self,
        max_action_retries: int = 2,
        max_replans: int = 3,
        max_total_failures: int = 5
    ):
        self.max_action_retries = max_action_retries
        self.max_replans = max_replans
        self.max_total_failures = max_total_failures

        self.action_retry_counts: Dict[str, int] = {}
        self.attempted_alternatives: set = set()
        self.replan_count: int = 0
        self.total_failure_count: int = 0

    def reset_for_new_task(self):
        self.action_retry_counts.clear()
        self.attempted_alternatives.clear()
        self.replan_count = 0
        self.total_failure_count = 0

    def get_alternative_tool(self, tool_name: str) -> Optional[str]:
        """Provides known tool fallbacks when a primary tool fails."""
        TOOL_ALTERNATIVES = {
            "cmd": "powershell",
            "powershell": "cmd",
            "mouse_click": "keyboard_press",  # e.g. press ENTER instead of clicking default button
            "keyboard_type": "write_file",     # e.g. write file directly instead of typing into GUI editor
        }
        return TOOL_ALTERNATIVES.get(tool_name)

    def determine_recovery_strategy(
        self,
        action_name: str,
        failure: FailureClassification
    ) -> Tuple[RecoveryAction, str, Optional[str]]:
        """
        Determines the next graduated recovery action and returns:
        (recovery_action, explanation, optional_alternative_tool_name)
        """
        self.total_failure_count += 1
        current_retries = self.action_retry_counts.get(action_name, 0)

        # Enforce global recovery limit
        if self.total_failure_count > self.max_total_failures:
            return (
                RecoveryAction.STOP,
                f"Exceeded total failure limit ({self.max_total_failures}). Halting to prevent system degradation.",
                None
            )

        # 1. PERMISSION FAILURES -> Cannot be resolved by retrying; must Ask User
        if failure.failure_type == FailureType.PERMISSION_FAILURE:
            return (
                RecoveryAction.ASK_USER,
                f"Action '{action_name}' requires elevated permission from the user: {failure.reason}",
                None
            )

        # 2. APPLICATION FAILURES -> Window hung or missing; Re-observe then replan
        if failure.failure_type == FailureType.APPLICATION_FAILURE:
            if current_retries == 0:
                self.action_retry_counts[action_name] = 1
                return (
                    RecoveryAction.OBSERVE_AGAIN,
                    f"Application state inconsistent ({failure.reason}). Re-observing desktop before proceeding.",
                    None
                )
            elif self.replan_count < self.max_replans:
                self.replan_count += 1
                return (
                    RecoveryAction.REPLAN,
                    f"Target application unrecoverable for '{action_name}'. Triggering replan.",
                    None
                )
            else:
                return (
                    RecoveryAction.ASK_USER,
                    f"Application failure persists and replan limit reached: {failure.reason}",
                    None
                )

        # 3. VERIFICATION OR TOOL FAILURES -> Graduated: Retry -> Alternative Tool -> Replan -> Ask User -> Stop
        if current_retries < self.max_action_retries:
            self.action_retry_counts[action_name] = current_retries + 1
            return (
                RecoveryAction.RETRY_SAFELY,
                f"Retrying action '{action_name}' (Attempt {current_retries + 1}/{self.max_action_retries}): {failure.reason}",
                None
            )

        # Check for Alternative Tool
        alt_tool = self.get_alternative_tool(action_name)
        if alt_tool and alt_tool not in self.action_retry_counts and alt_tool not in self.attempted_alternatives:
            self.attempted_alternatives.add(alt_tool)
            return (
                RecoveryAction.ALTERNATIVE_TOOL,
                f"Action '{action_name}' failed after retries. Attempting alternative tool '{alt_tool}'.",
                alt_tool
            )

        # Check for Replan
        if self.replan_count < self.max_replans:
            self.replan_count += 1
            return (
                RecoveryAction.REPLAN,
                f"Action '{action_name}' exhausted retries. Triggering intelligent replan: {failure.reason}",
                None
            )

        # Ask User fallback
        return (
            RecoveryAction.ASK_USER,
            f"Action '{action_name}' could not be completed and all autonomous recovery avenues exhausted: {failure.reason}",
            None
        )


# Global singleton instance
RECOVERY_ENGINE = RecoveryStrategyEngine()
