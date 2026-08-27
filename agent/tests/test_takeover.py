import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from agent.control.takeover import TakeoverManager, ControlState
from agent.core.state import StateTracker
from agent.core.executor import ToolExecutor
from agent.permissions.broker import PermissionBroker
from agent.permissions.policies import PolicyManager
from agent.tools import get_all_tools

@pytest.fixture
def takeover_manager():
    return TakeoverManager()

def test_control_state_transitions(takeover_manager):
    # Initial state
    assert takeover_manager.control_state == ControlState.AI_CONTROL
    assert not takeover_manager.is_takeover_active

    # Take control
    success = takeover_manager.take_control()
    assert success
    assert takeover_manager.control_state == ControlState.HUMAN_CONTROL
    assert takeover_manager.is_takeover_active

    # Duplicate take control (should be idempotent / True)
    success = takeover_manager.take_control()
    assert success

    # Release control
    success = takeover_manager.release_control()
    assert success
    assert takeover_manager.control_state == ControlState.AI_CONTROL
    assert not takeover_manager.is_takeover_active

    # Duplicate release control (should be idempotent / True)
    success = takeover_manager.release_control()
    assert success

@pytest.mark.asyncio
async def test_input_locking_during_takeover(takeover_manager):
    policy_manager = PolicyManager()
    state_tracker = StateTracker()
    permission_broker = PermissionBroker(policy_manager, state_tracker)
    tools = get_all_tools()
    executor = ToolExecutor(tools, permission_broker, takeover_manager)

    # 1. Takeover active -> execute_action should block with CONTROL_LOCKED
    takeover_manager.take_control()
    result = await executor.execute_action("launch_app", {"app_name": "notepad.exe"})
    assert not result["success"]
    assert result["error"] == "CONTROL_LOCKED"

    # 2. Release takeover -> execute_action should allow execution (e.g. check permission)
    takeover_manager.release_control()
    
    # Mock check_permission to return True
    with patch.object(permission_broker, "check_permission", return_value=True):
        # Mock tool execute
        with patch.dict(tools, {"launch_app": MagicMock()}):
            tools["launch_app"].execute = AsyncMock(return_value={"success": True})
            result = await executor.execute_action("launch_app", {"app_name": "notepad.exe"})
            assert result["success"]

@pytest.mark.asyncio
async def test_reobservation_and_replanning_on_release(takeover_manager):
    from agent.core.planner import RuleBasedPlanner
    from agent.models.api import ApiModelProvider
    
    planner = RuleBasedPlanner(ApiModelProvider(model_name="Gemini 3.5 Flash"))
    obs = {
        "active_window": {"title": "Paint", "process": "mspaint.exe"},
        "visible_windows": [{"title": "Paint", "process": "mspaint.exe"}],
        "screen": {"width": 1920, "height": 1080},
        "cursor": {"x": 500, "y": 500}
    }
    history = []
    
    # Takeover, make changes, then release
    takeover_manager.take_control()
    outcome = await planner.revalidate_plan("Open Paint and draw a house", [], obs, history)
    assert outcome == "replan"
