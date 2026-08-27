import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from agent.core.state import StateTracker
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.core.executor import ToolExecutor
from agent.core.planner import RuleBasedPlanner
from agent.core.loop import AgentLoop
from agent.tools import get_all_tools
from agent.core import win32_utils
from agent.core.action_validator import validate_action

@pytest.fixture(autouse=True)
def mock_win32_utils():
    """Mock win32_utils calls to avoid actual hardware clicks during tests."""
    with patch("agent.core.win32_utils.IS_WINDOWS", False), \
         patch("agent.core.win32_utils.get_active_window_details") as mock_active, \
         patch("agent.core.win32_utils.list_desktop_windows") as mock_list, \
         patch("agent.core.win32_utils.focus_window") as mock_focus, \
         patch("agent.core.win32_utils.type_text") as mock_type, \
         patch("agent.core.win32_utils.press_key") as mock_press, \
         patch("agent.core.win32_utils.hotkey") as mock_hotkey, \
         patch("agent.core.win32_utils.mouse_move") as mock_move, \
         patch("agent.core.win32_utils.mouse_down") as mock_down, \
         patch("agent.core.win32_utils.mouse_up") as mock_up, \
         patch("agent.core.win32_utils.mouse_drag") as mock_drag, \
         patch("agent.core.win32_utils.release_all_buttons") as mock_release, \
         patch("agent.core.win32_utils.get_screen_size", return_value=(1920, 1080)):
         
        mock_active.return_value = {
            "hwnd": 12345,
            "title": "Untitled - Paint",
            "process": "mspaint.exe",
            "pid": 1234,
            "bounds": {"x": 200, "y": 100, "width": 800, "height": 600}
        }
        
        mock_list.return_value = [
            {
                "hwnd": 12345,
                "title": "Untitled - Paint",
                "process": "mspaint.exe",
                "pid": 1234,
                "bounds": {"x": 200, "y": 100, "width": 800, "height": 600}
            }
        ]
        
        mock_focus.return_value = True
        
        yield {
            "active": mock_active,
            "list": mock_list,
            "focus": mock_focus,
            "type": mock_type,
            "press": mock_press,
            "hotkey": mock_hotkey,
            "move": mock_move,
            "down": mock_down,
            "up": mock_up,
            "drag": mock_drag,
            "release": mock_release
        }

# --- Action Validation Tests ---

def test_action_validation_mouse_move():
    # Valid
    ok, err = validate_action("mouse_move", {"x": 500, "y": 500, "duration_ms": 100})
    assert ok is True
    
    # Invalid coords
    ok, err = validate_action("mouse_move", {"x": 3000, "y": 500})
    assert ok is False
    assert "outside screen width bounds" in err
    
    # Invalid types
    ok, err = validate_action("mouse_move", {"x": "five", "y": 500})
    assert ok is False
    assert "must be integers" in err
    
    # Invalid duration
    ok, err = validate_action("mouse_move", {"x": 500, "y": 500, "duration_ms": -10})
    assert ok is False
    assert "Duration must be an integer" in err

def test_action_validation_mouse_click():
    # Valid
    ok, err = validate_action("mouse_click", {"x": 100, "y": 100, "button": "right", "click_count": 2})
    assert ok is True
    
    # Invalid button
    ok, err = validate_action("mouse_click", {"x": 100, "y": 100, "button": "scroll"})
    assert ok is False
    assert "Unsupported mouse button" in err
    
    # Invalid click count
    ok, err = validate_action("mouse_click", {"x": 100, "y": 100, "click_count": 10})
    assert ok is False
    assert "Click count must be an integer between 1 and 5" in err

def test_action_validation_keyboard():
    # Valid type
    ok, err = validate_action("keyboard_type", {"text": "Hello"})
    assert ok is True
    
    # Invalid type payload
    ok, err = validate_action("keyboard_type", {"text": 123})
    assert ok is False
    
    # Valid key press
    ok, err = validate_action("keyboard_press", {"key": "ENTER"})
    assert ok is True
    
    # Invalid key press
    ok, err = validate_action("keyboard_press", {"key": "FOO_BAR"})
    assert ok is False
    assert "Unrecognized keyboard key name" in err
    
    # Valid hotkey
    ok, err = validate_action("keyboard_hotkey", {"keys": ["CTRL", "SHIFT", "S"]})
    assert ok is True
    
    # Invalid hotkey item
    ok, err = validate_action("keyboard_hotkey", {"keys": ["CTRL", "INVALID_KEY"]})
    assert ok is False
    assert "Unrecognized keyboard key name" in err

# --- Coordinate Conversion Tests ---

def test_coordinate_conversion_valid():
    args = {"x": 100, "y": 150, "target_window": "Paint"}
    resolved, abs_x, abs_y, err = win32_utils.resolve_coordinates(args)
    assert resolved is True
    # Window is at x=200, y=100. Rel coords: 100, 150. Absolute should be 300, 250
    assert abs_x == 300
    assert abs_y == 250
    assert args["x"] == 300
    assert args["y"] == 250

def test_coordinate_conversion_missing_window():
    args = {"x": 100, "y": 150, "target_window": "Calculator"}
    resolved, abs_x, abs_y, err = win32_utils.resolve_coordinates(args)
    assert resolved is False
    assert "not found on the desktop" in err

# --- Action Routing & Tool Execution ---

@pytest.mark.asyncio
async def test_tool_routing():
    pm = PolicyManager()
    pm.update_policy("computer", "allow")
    broker = PermissionBroker(pm)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker)
    
    # Test routing to MouseClickTool
    result = await executor.execute_action("mouse_click", {"x": 100, "y": 100, "button": "left"})
    assert result["success"] is True
    assert "clicked" in result["output"]

# --- Cancellation & Cleanup ---

@pytest.mark.asyncio
async def test_agent_loop_cancellation_cleanup(mock_win32_utils):
    tracker = StateTracker()
    planner = RuleBasedPlanner(MagicMock())
    pm = PolicyManager()
    pm.update_policy("windows", "allow")
    pm.update_policy("computer", "allow")
    broker = PermissionBroker(pm)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker)
    takeover_manager = MagicMock()
    takeover_manager.is_takeover_active = False
    
    loop = AgentLoop(tracker, planner, executor, takeover_manager)
    
    # Request Stop
    loop.stop_task()
    
    # Verify the release_all_buttons mock was triggered to avoid stuck OS states
    assert mock_win32_utils["release"].call_count == 1

# --- Takeover Pausing & Button Release ---

@pytest.mark.asyncio
async def test_agent_loop_takeover_pausing(mock_win32_utils):
    tracker = StateTracker()
    planner = RuleBasedPlanner(MagicMock())
    pm = PolicyManager()
    pm.update_policy("windows", "allow")
    pm.update_policy("computer", "allow")
    broker = PermissionBroker(pm)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker)
    
    # Simulate active human takeover
    takeover_manager = MagicMock()
    takeover_manager.is_takeover_active = True
    
    async def mock_wait_takeover():
        await asyncio.sleep(5.0)
    takeover_manager.wait_if_takeover = mock_wait_takeover
    
    loop = AgentLoop(tracker, planner, executor, takeover_manager)
    
    # Start task
    loop.start_task("Open Paint and draw a house")
    
    # Sleep short time to allow OBSERVE and PLAN, then hit the step loop
    await asyncio.sleep(1.5)
    
    print(f"DIAGNOSTIC - status: {tracker.status}, error_message: {tracker.error_message}")
    # Verify that takeover was hit, loop paused, and held buttons were released
    assert tracker.status == "takeover"
    assert mock_win32_utils["release"].call_count == 1

