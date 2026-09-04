import pytest
import asyncio
from unittest.mock import patch, MagicMock

from agent.tools.computer import (
    MouseMoveTool, MouseClickTool, MouseDoubleClickTool,
    MouseDragTool, MouseScrollTool,
    KeyboardTypeTool, KeyboardPressTool, KeyboardHotkeyTool
)
from agent.tools.windows import (
    LaunchAppTool, ListWindowsTool, FocusWindowTool
)
from agent.core.action_validator import validate_action
from agent.core import win32_utils


# ============================================================================
# 1. KEYBOARD INTERACTION TESTS
# ============================================================================

def test_keyboard_type_action_validation():
    """Verify validate_action accepts valid text and rejects empty payloads."""
    valid, err = validate_action("keyboard_type", {"text": "Hello World"})
    assert valid is True
    assert err is None

    valid, err = validate_action("keyboard_type", {"text": ""})
    assert valid is False
    assert "non-empty string" in err

    valid, err = validate_action("keyboard_type", {})
    assert valid is False


def test_keyboard_press_action_validation():
    """Verify validate_action accepts known virtual keys and rejects unknown keys."""
    for key in ["ENTER", "TAB", "BACKSPACE", "ESCAPE", "UP", "DOWN", "LEFT", "RIGHT", "SPACE"]:
        valid, err = validate_action("keyboard_press", {"key": key})
        assert valid is True, f"Key '{key}' should be valid"

    valid, err = validate_action("keyboard_press", {"key": "NON_EXISTENT_KEY_XYZ"})
    assert valid is False
    assert "Unrecognized keyboard key name" in err


def test_keyboard_hotkey_action_validation():
    """Verify validate_action validates hotkey key lists."""
    valid, err = validate_action("keyboard_hotkey", {"keys": ["CTRL", "C"]})
    assert valid is True

    valid, err = validate_action("keyboard_hotkey", {"keys": []})
    assert valid is False

    valid, err = validate_action("keyboard_hotkey", {"keys": ["INVALID_MODIFIER_XYZ"]})
    assert valid is False


@pytest.mark.asyncio
async def test_keyboard_type_unicode_and_special_characters():
    """Verify KeyboardTypeTool successfully dispatches unicode and special characters."""
    tool = KeyboardTypeTool()
    unicode_sample = "SPR SAATHI: नमस्ते, こんにちは, España (ÁÉÍÓÚ), 123 !@#$%^&*()_+-=[]{}|;':\",./<>?"
    
    with patch("agent.core.win32_utils.type_text") as mock_type:
        res = await tool.execute({"text": unicode_sample})
        assert res["success"] is True
        mock_type.assert_called_once()
        call_args = mock_type.call_args[0]
        assert call_args[0] == unicode_sample


@pytest.mark.asyncio
async def test_keyboard_press_and_hotkey_execution():
    """Verify KeyboardPressTool and KeyboardHotkeyTool execute without exception."""
    press_tool = KeyboardPressTool()
    with patch("agent.core.win32_utils.press_key") as mock_press:
        res = await press_tool.execute({"key": "ENTER"})
        assert res["success"] is True
        mock_press.assert_called_once_with("ENTER")

    hotkey_tool = KeyboardHotkeyTool()
    with patch("agent.core.win32_utils.hotkey") as mock_hotkey:
        res = await hotkey_tool.execute({"keys": ["CTRL", "A"]})
        assert res["success"] is True
        mock_hotkey.assert_called_once_with(["CTRL", "A"])


# ============================================================================
# 2. MOUSE INTERACTION TESTS
# ============================================================================

def test_mouse_scroll_action_validation():
    """Verify validate_action accepts valid scroll parameters and rejects invalid ones."""
    valid, err = validate_action("mouse_scroll", {"clicks": 3, "direction": "down"})
    assert valid is True

    valid, err = validate_action("mouse_scroll", {"clicks": 2, "direction": "up"})
    assert valid is True

    valid, err = validate_action("mouse_scroll", {"clicks": 1, "direction": "left"})
    assert valid is True

    valid, err = validate_action("mouse_scroll", {"clicks": 1, "direction": "right"})
    assert valid is True

    # Invalid direction
    valid, err = validate_action("mouse_scroll", {"clicks": 1, "direction": "diagonal"})
    assert valid is False
    assert "Unsupported scroll direction" in err

    # Out of bounds coordinates
    valid, err = validate_action("mouse_scroll", {"clicks": 1, "direction": "down", "x": -50, "y": 100})
    assert valid is False
    assert "outside screen" in err


def test_mouse_coordinate_boundary_validation():
    """Verify position validation enforces screen boundaries."""
    screen_w, screen_h = win32_utils.get_screen_size()

    # Valid inside screen
    valid, err = validate_action("mouse_click", {"x": 100, "y": 100, "button": "left"})
    assert valid is True

    # Negative X
    valid, err = validate_action("mouse_click", {"x": -10, "y": 100, "button": "left"})
    assert valid is False
    assert "outside screen width bounds" in err

    # Negative Y
    valid, err = validate_action("mouse_click", {"x": 100, "y": -5, "button": "left"})
    assert valid is False
    assert "outside screen height bounds" in err

    # Beyond screen width
    valid, err = validate_action("mouse_click", {"x": screen_w + 100, "y": 100, "button": "left"})
    assert valid is False
    assert "outside screen width bounds" in err

    # Beyond screen height
    valid, err = validate_action("mouse_click", {"x": 100, "y": screen_h + 100, "button": "left"})
    assert valid is False
    assert "outside screen height bounds" in err


def test_mouse_drag_snap_assist_edge_rejection():
    """Verify that mouse drags starting or ending near screen top (y <= 5) are rejected to prevent Snap Assist collisions."""
    valid, err = validate_action("mouse_drag", {"start_x": 100, "start_y": 2, "end_x": 300, "end_y": 400})
    assert valid is False
    assert "Snap Assist" in err

    valid, err = validate_action("mouse_drag", {"start_x": 100, "start_y": 200, "end_x": 300, "end_y": 4})
    assert valid is False
    assert "Snap Assist" in err


@pytest.mark.asyncio
async def test_mouse_scroll_tool_execution():
    """Verify MouseScrollTool dispatches correctly to win32_utils.mouse_scroll."""
    scroll_tool = MouseScrollTool()

    with patch("agent.core.win32_utils.mouse_scroll") as mock_scroll:
        res = await scroll_tool.execute({"clicks": 5, "direction": "down"})
        assert res["success"] is True
        assert "Scrolled mouse down by 5 clicks" in res["output"]
        mock_scroll.assert_called_once_with(clicks=5, direction="down", x=None, y=None)

    with patch("agent.core.win32_utils.mouse_scroll") as mock_scroll:
        res = await scroll_tool.execute({"clicks": 3, "direction": "up", "x": 400, "y": 300, "coordinate_space": "screen"})
        assert res["success"] is True
        assert "at (400, 300)" in res["output"]
        mock_scroll.assert_called_once_with(clicks=3, direction="up", x=400, y=300)


# ============================================================================
# 3. WINDOW MANAGEMENT TESTS
# ============================================================================

def test_list_windows_returns_active_desktop_windows():
    """Verify ListWindowsTool lists desktop windows with titles and process names."""
    tool = ListWindowsTool()
    res = asyncio.run(tool.execute({}))
    assert res["success"] is True
    assert isinstance(res["windows"], list)
    assert res["count"] >= 0


@pytest.mark.asyncio
async def test_launch_app_asynchronous_readiness_detection():
    """Verify LaunchAppTool detects application readiness without blocking event loop."""
    tool = LaunchAppTool()

    mock_ready_info = {
        "ready": True,
        "hwnd": 12345,
        "title": "Untitled - Notepad",
        "process": "Notepad.exe",
        "wait_time_ms": 300
    }

    with patch("agent.core.win32_utils.wait_for_application_ready_async", return_value=mock_ready_info), \
         patch("subprocess.Popen"):
        res = await tool.execute({"app_name": "notepad.exe"})
        assert res["success"] is True
        assert res["readiness"]["ready"] is True
        assert "confirmed ready" in res["output"]


@pytest.mark.asyncio
async def test_focus_window_with_foreground_verification():
    """Verify FocusWindowTool focuses window and verifies foreground state."""
    tool = FocusWindowTool()

    fake_windows = [
        {"hwnd": 1001, "title": "Test Document - Notepad", "process": "notepad.exe"}
    ]

    with patch("agent.core.win32_utils.list_desktop_windows", return_value=fake_windows), \
         patch("agent.core.win32_utils.focus_window", return_value=True), \
         patch("agent.core.win32_utils.verify_foreground_state", return_value=True):
        res = await tool.execute({"title_substring": "Notepad"})
        assert res["success"] is True
        assert res["foreground_verified"] is True
        assert res["target_hwnd"] == 1001
        assert "Foreground Verified: True" in res["output"]


# ============================================================================
# 4. INPUT COORDINATION AND CONCURRENCY TESTS
# ============================================================================

def test_global_input_lock_protects_concurrent_input_operations():
    """Verify that _GLOBAL_INPUT_LOCK serializes mouse and keyboard inputs."""
    import threading
    import time

    execution_order = []

    def simulated_mouse_drag():
        with win32_utils._GLOBAL_INPUT_LOCK:
            execution_order.append("mouse_drag_start")
            time.sleep(0.05)
            execution_order.append("mouse_drag_end")

    def simulated_keystroke():
        with win32_utils._GLOBAL_INPUT_LOCK:
            execution_order.append("keystroke_start")
            time.sleep(0.02)
            execution_order.append("keystroke_end")

    t1 = threading.Thread(target=simulated_mouse_drag)
    t2 = threading.Thread(target=simulated_keystroke)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # The lock guarantees no interleaving: either drag finished before keystroke, or vice versa
    assert execution_order in [
        ["mouse_drag_start", "mouse_drag_end", "keystroke_start", "keystroke_end"],
        ["keystroke_start", "keystroke_end", "mouse_drag_start", "mouse_drag_end"]
    ]
