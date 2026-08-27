import pytest
import asyncio
from unittest.mock import patch, MagicMock

from agent.core.state import StateTracker
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.core.executor import ToolExecutor
from agent.core.planner import RuleBasedPlanner
from agent.core.loop import AgentLoop
from agent.tools import get_all_tools

@pytest.fixture(autouse=True)
def mock_win32_utils():
    """Mock win32_utils to avoid actual OS calls during unit tests."""
    with patch("agent.core.win32_utils.IS_WINDOWS", False), \
         patch("agent.core.win32_utils.get_active_window_details") as mock_active, \
         patch("agent.core.win32_utils.list_desktop_windows") as mock_list, \
         patch("agent.core.win32_utils.focus_window") as mock_focus, \
         patch("agent.core.win32_utils.type_text") as mock_type, \
         patch("agent.core.win32_utils.press_key") as mock_press, \
         patch("agent.core.win32_utils.hotkey") as mock_hotkey:
         
        mock_active.return_value = {
            "hwnd": 12345,
            "title": "Untitled - Notepad",
            "process": "notepad.exe",
            "pid": 1234,
            "bounds": {"x": 100, "y": 100, "width": 800, "height": 600}
        }
        
        mock_list.return_value = [
            {
                "hwnd": 12345,
                "title": "Untitled - Notepad",
                "process": "notepad.exe",
                "pid": 1234,
                "bounds": {"x": 100, "y": 100, "width": 800, "height": 600}
            }
        ]
        
        mock_focus.return_value = True
        
        yield {
            "active": mock_active,
            "list": mock_list,
            "focus": mock_focus,
            "type": mock_type,
            "press": mock_press,
            "hotkey": mock_hotkey
        }

def test_state_tracker():
    tracker = StateTracker()
    assert tracker.status == "idle"
    tracker.reset("Open Notepad")
    assert tracker.current_task == "Open Notepad"
    assert tracker.task_id is not None
    
    tracker.set_steps(["Step 1", "Step 2"])
    assert len(tracker.steps) == 2
    assert tracker.steps[0]["status"] == "pending"
    
    tracker.start_step("step_1")
    assert tracker.steps[0]["status"] == "running"
    
    tracker.complete_step("step_1")
    assert tracker.steps[0]["status"] == "completed"

def test_policy_manager():
    pm = PolicyManager()
    assert pm.get_policy("mouse_move", "computer") == "prompt"
    assert pm.get_policy("launch_app", "windows") == "allow"
    
    pm.update_policy("computer", "allow")
    assert pm.get_policy("mouse_move", "computer") == "allow"

@pytest.mark.asyncio
async def test_permission_broker_allow():
    pm = PolicyManager()
    broker = PermissionBroker(pm)
    pm.update_policy("windows", "allow")
    
    allowed = await broker.check_permission("launch_app", "windows", {})
    assert allowed is True

@pytest.mark.asyncio
async def test_permission_broker_deny():
    pm = PolicyManager()
    broker = PermissionBroker(pm)
    pm.update_policy("terminal", "deny")
    
    allowed = await broker.check_permission("cmd", "terminal", {})
    assert allowed is False

@pytest.mark.asyncio
async def test_permission_broker_prompt():
    pm = PolicyManager()
    broker = PermissionBroker(pm)
    pm.update_policy("computer", "prompt")
    
    prompted = False
    async def mock_callback(request_id, tool_name, arguments):
        nonlocal prompted
        prompted = True
        # Resolve it
        broker.resolve_permission(request_id, "allow")

    broker.on_prompt_callback = mock_callback
    allowed = await broker.check_permission("mouse_move", "computer", {"x": 10, "y": 20})
    
    assert prompted is True
    assert allowed is True

@pytest.mark.asyncio
async def test_tool_executor_with_denied_permission():
    pm = PolicyManager()
    broker = PermissionBroker(pm)
    pm.update_policy("filesystem", "deny")
    
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker)
    
    result = await executor.execute_action("create_file", {"filepath": "test.txt", "content": "hello"})
    assert result["success"] is False
    assert "Permission denied" in result["error"]

@pytest.mark.asyncio
async def test_planner_decomposition():
    # Setup mock provider
    mock_provider = MagicMock()
    planner = RuleBasedPlanner(mock_provider)
    
    # 1. Notepad launch and type decomposition
    steps, calls = await planner.create_plan("Open Notepad and type Hello SPR Saathi", "Desktop")
    assert len(steps) == 3
    assert len(calls) == 3
    assert calls[0]["tool_name"] == "launch_app"
    assert calls[1]["tool_name"] == "focus_window"
    assert calls[2]["tool_name"] == "keyboard_type"
    assert calls[2]["arguments"]["text"] == "Hello SPR Saathi"
    
    # 2. Just app launch
    steps, calls = await planner.create_plan("Open Paint", "Desktop")
    assert len(steps) == 1
    assert calls[0]["tool_name"] == "launch_app"
    assert calls[0]["arguments"]["app_name"] == "mspaint.exe"

@pytest.mark.asyncio
async def test_agent_loop_execution(mock_win32_utils):
    # Setup components
    tracker = StateTracker()
    mock_provider = MagicMock()
    planner = RuleBasedPlanner(mock_provider)
    pm = PolicyManager()
    # Allow windows & computer actions to bypass prompts for loop speed test
    pm.update_policy("windows", "allow")
    pm.update_policy("computer", "allow")
    broker = PermissionBroker(pm)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker)
    takeover_manager = MagicMock()
    takeover_manager.is_takeover_active = False
    
    events = []
    async def mock_broadcast(event):
        events.append(event)

    loop = AgentLoop(tracker, planner, executor, takeover_manager, mock_broadcast)
    
    # Execute notepad typing task
    loop.start_task("Open Notepad and type Hello SPR Saathi")
    
    # Wait for the task task loop task to complete
    await asyncio.sleep(4.5)
    
    assert tracker.status == "completed"
    assert len(tracker.steps) == 3
    assert tracker.steps[0]["status"] == "completed"
    assert tracker.steps[1]["status"] == "completed"
    assert tracker.steps[2]["status"] == "completed"
    
    # Verify Win32 utilities were invoked
    assert mock_win32_utils["type"].call_count == 1
    mock_win32_utils["type"].assert_called_with("Hello SPR Saathi")
