import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from agent.core.uncertainty import (
    UncertaintyDetector, UncertaintyTrigger, UNCERTAINTY_DETECTOR
)
from agent.core.loop import AgentLoop
from agent.core.state import StateTracker
from agent.core.planner import RuleBasedPlanner
from agent.core.executor import ToolExecutor
from agent.control.takeover import TakeoverManager
from agent.models.base import BaseModelProvider, ModelResponse


class MockModel(BaseModelProvider):
    def __init__(self, model_name: str = "mock"):
        super().__init__(model_name=model_name)

    async def generate(self, prompt, system_instruction=None, image_bytes=None):
        return ModelResponse(text='{"decision_type": "ask_user", "question": "Which file should I edit?"}')

    async def decide_action(self, prompt, system_instruction=None, image_bytes=None, tools=None):
        return {"decision_type": "ask_user", "question": "Which file should I edit?"}

    async def generate_with_tools(self, prompt, tools, system_instruction=None, image_bytes=None):
        return {"decision_type": "ask_user", "question": "Which file should I edit?"}


# ============================================================================
# 1. UNCERTAINTY DETECTION TRIGGERS
# ============================================================================

def test_multiple_files_uncertainty_trigger():
    """Verify uncertainty triggered when multiple files match ambiguous query."""
    files = ["report_q1.xlsx", "report_q2.xlsx", "report_final.xlsx"]
    should_ask, question = UncertaintyDetector.check_file_ambiguity(files, "the report")

    assert should_ask is True
    assert "Multiple files match" in question
    assert "report_q1.xlsx" in question


def test_destructive_operation_uncertainty_trigger():
    """Verify uncertainty triggered on destructive shell commands."""
    args = {"command": "rmdir /s /q C:\\ImportantProject"}
    should_ask, question = UncertaintyDetector.check_destructive_uncertainty("cmd", args)

    assert should_ask is True
    assert "potentially destructive" in question


def test_conflicting_instructions_trigger():
    """Verify uncertainty triggered when user instructions conflict."""
    should_ask, q = UncertaintyDetector.check_instruction_conflict("Delete the logs but keep the error logs")
    assert should_ask is True
    assert "deleting and keeping" in q


def test_ambiguous_short_request_trigger():
    """Verify brief ambiguous requests trigger clarification."""
    should_ask, q = UncertaintyDetector.check_ambiguity("clean it")
    assert should_ask is True
    assert "brief" in q


# ============================================================================
# 2. ASK USER WORKFLOW & RESUME
# ============================================================================

@pytest.mark.asyncio
async def test_ask_user_workflow_and_response_resolution():
    """Verify AgentLoop pauses on ask_user and cleanly resumes when submit_user_response is called."""
    st = StateTracker()
    loop = AgentLoop(
        state_tracker=st,
        planner=MagicMock(),
        executor=MagicMock(),
        takeover_manager=MagicMock()
    )

    # Simulate waiting for user answer
    loop._user_response_future = asyncio.get_running_loop().create_future()
    assert loop._user_response_future.done() is False

    # Submit answer
    success = loop.submit_user_response("Please edit report_q2.xlsx")
    assert success is True
    assert loop._user_response_future.done() is True
    assert loop._user_response_future.result() == "Please edit report_q2.xlsx"
