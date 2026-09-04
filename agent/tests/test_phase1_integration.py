import pytest
import asyncio
from typing import List, Dict, Any, Optional

from agent.core.action import Action, ActionStatus, VerificationStatus
from agent.core.task_manager import TaskManager
from agent.core.state import StateTracker
from agent.core.executor import ToolExecutor
from agent.core.loop import AgentLoop
from agent.core.planner import RuleBasedPlanner
from agent.control.takeover import TakeoverManager
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.tools.base import BaseTool
from agent.models.base import BaseModelProvider, ModelResponse


class StepTrackingTool(BaseTool):
    def __init__(self, name: str = "step_tool"):
        self._name = name
        self.invocations: List[Dict[str, Any]] = []
        self.should_fail_first: bool = False
        self._failed_once: bool = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Tool for testing loop execution"

    @property
    def category(self) -> str:
        return "windows"

    @property
    def required_scope(self) -> str:
        return "windows"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"step_num": {"type": "integer"}}}

    async def execute(self, arguments):
        self.invocations.append(arguments)
        if self.should_fail_first and not self._failed_once:
            self._failed_once = True
            raise RuntimeError("Temporary simulated execution failure")
        return {"success": True, "output": f"Successfully completed step {arguments.get('step_num')}"}


class SequentialModelProvider(BaseModelProvider):
    """Feeds decisions in exact order."""
    def __init__(self, decisions: List[Dict[str, Any]]):
        super().__init__(model_name="sequential_mock")
        self.decisions = decisions
        self.idx = 0

    @property
    def capabilities(self):
        return {"supports_vision": False}

    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> ModelResponse:
        return ModelResponse(text="{}")

    async def generate_with_tools(self, prompt: str, tools, system_instruction: Optional[str] = None) -> ModelResponse:
        return ModelResponse(text="{}")

    async def decide_action(self, goal, plan, observation, recent_history, image_base64=None):
        if self.idx < len(self.decisions):
            decision = self.decisions[self.idx]
            self.idx += 1
            return decision
        return {"decision_type": "final", "message": "All sequential decisions processed"}


@pytest.mark.asyncio
async def test_end_to_end_successful_execution_loop():
    """
    Validates complete end-to-end flow:
    Task Creation -> Planning -> Action Execution -> Action Verification -> Status Recording -> Completion.
    """
    tool = StepTrackingTool("step_tool")
    state_tracker = StateTracker()
    task_manager = TaskManager(state_tracker=state_tracker)
    policy_mgr = PolicyManager()
    policy_mgr.update_policy("windows", "allow")
    broker = PermissionBroker(policy_mgr, state_tracker)
    takeover = TakeoverManager()
    executor = ToolExecutor({"step_tool": tool}, broker, takeover)

    # 2 sequential steps then final
    decisions = [
        {"decision_type": "tool_call", "tool_name": "step_tool", "arguments": {"step_num": 1}},
        {"decision_type": "tool_call", "tool_name": "step_tool", "arguments": {"step_num": 2}},
        {"decision_type": "final", "message": "Integration task finished successfully"}
    ]
    model_provider = SequentialModelProvider(decisions)
    planner = RuleBasedPlanner(model_provider)

    events = []
    async def capture_event(ev):
        events.append(ev)

    loop = AgentLoop(
        state_tracker=state_tracker,
        planner=planner,
        executor=executor,
        takeover_manager=takeover,
        broadcast_callback=capture_event,
        task_manager=task_manager
    )

    # Start task
    loop.start_task("Perform full integration run")
    
    # Wait for loop to run to completion
    for _ in range(50):
        if state_tracker.status in ["completed", "failed", "cancelled"]:
            break
        await asyncio.sleep(0.1)

    # 1. Verification of Task Lifecycle
    assert state_tracker.status == "completed"
    task = task_manager.get_active_task()
    assert task is not None
    assert task.status == "completed"
    assert task.completed_at is not None

    # 2. Verification of Tool Invocations
    assert len(tool.invocations) == 2
    assert tool.invocations[0] == {"step_num": 1, "call_id": task.actions[0].action_id, "task_id": task.task_id}
    assert tool.invocations[1] == {"step_num": 2, "call_id": task.actions[1].action_id, "task_id": task.task_id}

    # 3. Verification of Action Identity & History Recording
    assert len(task.actions) == 2
    act1 = task.actions[0]
    act2 = task.actions[1]
    assert act1.action_id != act2.action_id
    assert act1.status == ActionStatus.COMPLETED
    assert act2.status == ActionStatus.COMPLETED
    assert act1.verification_status == VerificationStatus.VERIFIED_SUCCESS
    assert act2.verification_status == VerificationStatus.VERIFIED_SUCCESS

    # 4. StateTracker Action History Check
    assert len(state_tracker.action_history) == 2
    assert state_tracker.action_history[0]["action_id"] == act1.action_id
    assert state_tracker.action_history[0]["verification_status"] == "verified_success"
    assert state_tracker.action_history[1]["action_id"] == act2.action_id
    assert state_tracker.action_history[1]["verification_status"] == "verified_success"

    # 5. Broadcast Event Trace Check
    event_types = [e["event_type"] for e in events]
    assert "task.created" in event_types
    assert "task.planning" in event_types
    assert "tool.requested" in event_types
    assert "tool.completed" in event_types
    assert "task.completed" in event_types


@pytest.mark.asyncio
async def test_end_to_end_failure_replan_and_recovery_loop():
    """
    Validates recovery flow:
    Failed Action -> Re-observation -> Replanning -> Recovery Action -> Verification -> Completion.
    """
    tool = StepTrackingTool("recovery_tool")
    tool.should_fail_first = True  # Step 1 will fail on first try

    state_tracker = StateTracker()
    task_manager = TaskManager(state_tracker=state_tracker)
    policy_mgr = PolicyManager()
    policy_mgr.update_policy("windows", "allow")
    broker = PermissionBroker(policy_mgr, state_tracker)
    takeover = TakeoverManager()
    executor = ToolExecutor({"recovery_tool": tool}, broker, takeover)

    # 1st: try step 1 (fails)
    # 2nd: replan
    # 3rd: retry step 1 (succeeds)
    # 4th: final
    decisions = [
        {"decision_type": "tool_call", "tool_name": "recovery_tool", "arguments": {"step_num": 10}},
        {"decision_type": "replan", "reason": "Previous step failed, re-adjusting parameters"},
        {"decision_type": "tool_call", "tool_name": "recovery_tool", "arguments": {"step_num": 10}},
        {"decision_type": "final", "message": "Recovered and finished successfully"}
    ]
    model_provider = SequentialModelProvider(decisions)
    planner = RuleBasedPlanner(model_provider)

    events = []
    async def capture_event(ev):
        events.append(ev)

    loop = AgentLoop(
        state_tracker=state_tracker,
        planner=planner,
        executor=executor,
        takeover_manager=takeover,
        broadcast_callback=capture_event,
        task_manager=task_manager
    )

    loop.start_task("Test failure recovery loop")
    
    for _ in range(50):
        if state_tracker.status in ["completed", "failed", "cancelled"]:
            break
        await asyncio.sleep(0.1)

    assert state_tracker.status == "completed"
    task = task_manager.get_active_task()
    assert task is not None
    assert task.status == "completed"

    # Action history should reflect 1 failed action followed by 1 successful recovery action
    assert len(task.actions) == 2
    assert task.actions[0].status == ActionStatus.FAILED
    assert task.actions[0].verification_status == VerificationStatus.VERIFICATION_FAILED
    assert task.actions[1].status == ActionStatus.COMPLETED
    assert task.actions[1].verification_status == VerificationStatus.VERIFIED_SUCCESS

    event_types = [e["event_type"] for e in events]
    assert "tool.failed" in event_types
    assert "task.replanning" in event_types
    assert "tool.completed" in event_types
    assert "task.completed" in event_types
