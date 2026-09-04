import pytest
import asyncio
import uuid
import datetime
from typing import Optional, List, Dict, Any
from unittest.mock import AsyncMock, MagicMock

from agent.core.action import Action, ActionStatus, VerificationStatus
from agent.core.task_manager import Task, TaskManager
from agent.core.state import StateTracker
from agent.core.executor import ToolExecutor
from agent.core.loop import AgentLoop
from agent.core.planner import RuleBasedPlanner
from agent.control.takeover import TakeoverManager
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.tools.base import BaseTool
from agent.models.base import BaseModelProvider, ModelResponse

# Helper Dummy Tool
class DummyTool(BaseTool):
    def __init__(self, name: str = "dummy_tool", delay: float = 0.0, fail: bool = False):
        self._name = name
        self.delay = delay
        self.fail = fail
        self.execution_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A dummy test tool"

    @property
    def category(self) -> str:
        return "windows"

    @property
    def required_scope(self) -> str:
        return "windows"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"val": {"type": "string"}}}

    async def execute(self, arguments):
        self.execution_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("Intentional tool error")
        return {"success": True, "output": f"Executed with {arguments.get('val')}"}


# Mock Model Provider
class MockModelProvider(BaseModelProvider):
    def __init__(self, decisions=None):
        super().__init__(model_name="mock_model")
        self.decisions = decisions or []
        self.decision_idx = 0

    @property
    def capabilities(self):
        return {"supports_vision": False}

    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> ModelResponse:
        return ModelResponse(text="{}")

    async def generate_with_tools(self, prompt: str, tools, system_instruction: Optional[str] = None) -> ModelResponse:
        return ModelResponse(text="{}")

    async def decide_action(self, goal, plan, observation, recent_history, image_base64=None):
        if self.decision_idx < len(self.decisions):
            d = self.decisions[self.decision_idx]
            self.decision_idx += 1
            return d
        return {"decision_type": "final", "message": "All mock decisions completed"}


# ============================================================================
# 1. TASK TESTS
# ============================================================================

def test_task_creation_and_unique_identity():
    """Verify tasks are assigned unique UUIDs, timestamps, and created state."""
    tm = TaskManager()
    t1 = tm.create_task("Task 1 goal")
    t2 = tm.create_task_after = TaskManager()  # another manager
    t2 = tm.create_task("Task 2 goal") if not tm.get_active_task() or tm.get_active_task().status in ["completed"] else None
    
    # Force complete t1
    tm.update_task_status(t1.task_id, "completed")
    t2 = tm.create_task("Task 2 goal")

    assert t1.task_id != t2.task_id
    assert uuid.UUID(t1.task_id)  # valid UUID
    assert uuid.UUID(t2.task_id)
    assert t1.goal == "Task 1 goal"
    assert t2.goal == "Task 2 goal"
    assert t1.created_at is not None
    assert t2.created_at is not None
    assert t2.status == "created"


def test_task_lifecycle_transitions():
    """Verify task state transitions: created -> running -> completed."""
    state_tracker = StateTracker()
    tm = TaskManager(state_tracker=state_tracker)
    task = tm.create_task("Sample Task")
    
    assert task.status == "created"
    assert state_tracker.status == "queued"

    tm.update_task_status(task.task_id, "running")
    assert task.status == "running"
    assert task.started_at is not None
    assert state_tracker.status == "running"

    tm.update_task_status(task.task_id, "completed")
    assert task.status == "completed"
    assert task.completed_at is not None
    assert state_tracker.status == "completed"


def test_task_manager_single_active_task_concurrency():
    """Verify that starting a task when one is already running raises RuntimeError."""
    tm = TaskManager()
    t1 = tm.create_task("Running Task")
    t1.update_status("running")

    with pytest.raises(RuntimeError) as exc_info:
        tm.create_task("Concurrent Task Attempt")
    assert "is currently running" in str(exc_info.value)


def test_task_history_persistence():
    """Verify that TaskManager retains historical tasks across completions."""
    tm = TaskManager()
    t1 = tm.create_task("History Task 1")
    t1.update_status("completed")

    t2 = tm.create_task("History Task 2")
    t2.update_status("completed")

    all_tasks = tm.list_tasks()
    assert len(all_tasks) == 2
    task_ids = [t["task_id"] for t in all_tasks]
    assert t1.task_id in task_ids
    assert t2.task_id in task_ids


# ============================================================================
# 2. ACTION TESTS
# ============================================================================

def test_action_identity_attributes():
    """Verify that an Action maintains all 8 Phase 1 required attributes."""
    action = Action(
        task_id="task_123",
        action_type="mouse_click",
        arguments={"x": 100, "y": 200},
        step_id="step_1"
    )

    d = action.to_dict()
    assert "action_id" in d
    assert d["action_id"].startswith("act_")
    assert d["task_id"] == "task_123"
    assert d["action_type"] == "mouse_click"
    assert d["arguments"] == {"x": 100, "y": 200}
    assert d["status"] == "pending"
    assert d["timestamp"] is not None
    assert d["verification_status"] == "unverified"


def test_action_state_transitions():
    """Verify Action state progression: pending -> executing -> completed."""
    action = Action(task_id="t1", action_type="draw_line", arguments={})
    assert action.status == ActionStatus.PENDING

    action.start_execution()
    assert action.status == ActionStatus.EXECUTING

    action.complete(output="Drawn", duration_ms=50, verification_status=VerificationStatus.VERIFIED_SUCCESS)
    assert action.status == ActionStatus.COMPLETED
    assert action.output == "Drawn"
    assert action.verification_status == VerificationStatus.VERIFIED_SUCCESS
    assert action.duration_ms == 50


@pytest.mark.asyncio
async def test_duplicate_dispatch_prevention_for_same_action_id():
    """Verify that dispatching the same action ID twice returns the cached result."""
    tool = DummyTool("test_tool")
    policy_mgr = PolicyManager()
    policy_mgr.update_policy("windows", "allow")
    executor = ToolExecutor({"test_tool": tool}, PermissionBroker(policy_mgr))

    res1 = await executor.execute_action("test_tool", {"val": "1"}, call_id="act_unique_001", task_id="t1")
    assert res1["success"] is True
    assert tool.execution_count == 1
    assert "duplicate_dispatch_prevented" not in res1

    # Second dispatch with identical action ID
    res2 = await executor.execute_action("test_tool", {"val": "1"}, call_id="act_unique_001", task_id="t1")
    assert res2["success"] is True
    assert res2.get("duplicate_dispatch_prevented") is True
    assert tool.execution_count == 1  # Tool was NOT called a second time


@pytest.mark.asyncio
async def test_legitimate_identical_actions_with_different_action_ids():
    """
    Verify that two legitimate actions with IDENTICAL arguments execute both times
    as long as they have different action IDs (Requirement Rule: no argument-based deduplication).
    """
    tool = DummyTool("click_tool")
    policy_mgr = PolicyManager()
    policy_mgr.update_policy("windows", "allow")
    executor = ToolExecutor({"click_tool": tool}, PermissionBroker(policy_mgr))

    # First click at (50, 50)
    res1 = await executor.execute_action("click_tool", {"x": 50, "y": 50}, call_id="act_click_1", task_id="t1")
    assert res1["success"] is True
    assert tool.execution_count == 1

    # Second click at the exact same (50, 50) coordinates but with a new unique action ID
    res2 = await executor.execute_action("click_tool", {"x": 50, "y": 50}, call_id="act_click_2", task_id="t1")
    assert res2["success"] is True
    assert tool.execution_count == 2  # Both clicks executed!
    assert "duplicate_dispatch_prevented" not in res2


# ============================================================================
# 3. CONCURRENCY & CANCELLATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_stop_during_execution():
    """Verify that calling stop_task() immediately cancels loop and sets cancelled status."""
    tool = DummyTool("slow_tool", delay=1.0)
    state_tracker = StateTracker()
    tm = TaskManager(state_tracker=state_tracker)
    policy_mgr = PolicyManager()
    policy_mgr.update_policy("windows", "allow")
    broker = PermissionBroker(policy_mgr, state_tracker)
    takeover = TakeoverManager()
    executor = ToolExecutor({"slow_tool": tool}, broker, takeover)

    mock_provider = MockModelProvider([
        {"decision_type": "tool_call", "tool_name": "slow_tool", "arguments": {"val": "slow"}},
        {"decision_type": "final", "message": "Done"}
    ])
    planner = RuleBasedPlanner(mock_provider)
    loop = AgentLoop(state_tracker, planner, executor, takeover, task_manager=tm)

    loop.start_task("Long running task")
    await asyncio.sleep(0.2)  # Let it enter tool execution

    # Cancel while tool is in progress
    loop.stop_task()
    await asyncio.sleep(0.2)

    assert state_tracker.status == "cancelled"
    task = tm.get_active_task()
    assert task.status == "cancelled"


@pytest.mark.asyncio
async def test_pause_and_resume_preserves_plan():
    """
    Verify that pausing execution for takeover and resuming does NOT wipe out the existing checklist
    or restart from step 1.
    """
    tool = DummyTool("quick_tool", delay=0.01)
    state_tracker = StateTracker()
    tm = TaskManager(state_tracker=state_tracker)
    policy_mgr = PolicyManager()
    policy_mgr.update_policy("windows", "allow")
    broker = PermissionBroker(policy_mgr, state_tracker)
    takeover = TakeoverManager()
    executor = ToolExecutor({"quick_tool": tool}, broker, takeover)

    mock_provider = MockModelProvider([
        {"decision_type": "tool_call", "tool_name": "quick_tool", "arguments": {"val": "1"}},
        {"decision_type": "tool_call", "tool_name": "quick_tool", "arguments": {"val": "2"}},
        {"decision_type": "final", "message": "Done"}
    ])
    planner = RuleBasedPlanner(mock_provider)
    loop = AgentLoop(state_tracker, planner, executor, takeover, task_manager=tm)

    loop.start_task("Multi step task")
    await asyncio.sleep(0.1)

    # Pause task
    loop.pause_task_for_takeover()
    assert takeover.is_takeover_active is True
    assert state_tracker.status == "paused"
    
    # Verify steps exist and were not deleted
    steps_at_pause = list(state_tracker.steps)
    assert len(steps_at_pause) > 0

    # Resume task
    resumed = await loop.resume_task_after_takeover()
    assert resumed is True
    assert takeover.is_takeover_active is False
    
    # Verify the plan checklist was preserved and not wiped out
    assert len(state_tracker.steps) == len(steps_at_pause)
    loop.stop_task()


@pytest.mark.asyncio
async def test_late_permission_response_after_cancellation():
    """
    Verify that resolving a permission request after task cancellation fails safely
    and does not trigger tool execution.
    """
    policy_mgr = PolicyManager()
    policy_mgr.update_policy("windows", "prompt")  # Require prompt
    broker = PermissionBroker(policy_mgr)

    # Trigger permission prompt
    async def fake_prompt(req_id, tool_name, args):
        pass
    broker.on_prompt_callback = fake_prompt

    # Start checking permission in background
    check_task = asyncio.create_task(broker.check_permission("test_tool", "windows", {}))
    await asyncio.sleep(0.05)

    # Now cancel all pending requests (as stop_task does)
    broker.cancel_all_pending()

    # Attempt to submit late permission response
    resolved = broker.resolve_permission("non_existent_or_cancelled_id", "allow")
    assert resolved is False

    # Check task should raise CancelledError due to cancellation
    with pytest.raises(asyncio.CancelledError):
        await check_task
