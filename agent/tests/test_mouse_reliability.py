import pytest
import asyncio
import os
import threading
import time
from PIL import Image

from agent.core import win32_utils
from agent.core.vision import verify_visual_change, ScreenObserver
from agent.core.action_validator import validate_action
from agent.core.context import build_observation_summary, build_system_instruction, build_tools_catalog
from agent.tools import get_all_tools
from agent.tools.computer import MouseDragTool, MouseClickTool, MouseMoveTool
from agent.tools.drawing import DrawLineTool, DrawPolylineTool, DrawRectangleTool, DrawShapeTool

def test_context_observation_summary_no_name_error():
    """Verify build_observation_summary executes without NameError: name 'win32_utils' is not defined."""
    mock_obs = {
        "active_window": {
            "hwnd": 1234,
            "title": "Untitled - Paint",
            "process": "mspaint.exe",
            "bounds": {"x": 0, "y": 80, "width": 1920, "height": 1080}
        },
        "visible_windows": [],
        "cursor": {"x": 500, "y": 500},
        "screen": {"width": 1920, "height": 1080}
    }
    summary = build_observation_summary(mock_obs)
    assert "Untitled - Paint" in summary
    assert "Usable Content/Canvas Area" in summary
    
    prompt = build_system_instruction()
    assert "draw_shape" in prompt
    catalog = build_tools_catalog()
    assert "draw_shape" in catalog
    assert "draw_line" in catalog


def test_get_window_content_bounds_paint():
    """Verify usable content calculation safely excludes title bar and ribbon."""
    mock_paint_win = {
        "title": "Untitled - Paint",
        "process": "mspaint.exe",
        "bounds": {"x": 100, "y": 80, "width": 1200, "height": 800}
    }
    content = win32_utils.get_window_content_bounds(mock_paint_win)
    assert content["is_canvas"] is True
    assert content["y"] >= mock_paint_win["bounds"]["y"] + 200, "Content Y must start below the ribbon toolbar"
    assert content["width"] > 0
    assert content["height"] > 0


def test_resolve_coordinates_content_space():
    """Verify coordinate resolution maps content-relative coordinates safely."""
    mock_win = {
        "hwnd": 1234,
        "title": "Test App",
        "process": "notepad.exe",
        "bounds": {"x": 50, "y": 50, "width": 800, "height": 600}
    }
    args = {
        "start_x": 10, "start_y": 10,
        "end_x": 100, "end_y": 100,
        "target_window": "Test App",
        "coordinate_space": "content"
    }
    orig_list = win32_utils.list_desktop_windows
    win32_utils.list_desktop_windows = lambda: [mock_win]
    try:
        resolved, coords, err = win32_utils.resolve_coordinates(args)
        assert resolved is True
        assert coords is not None
        assert coords["start_y"] >= mock_win["bounds"]["y"] + 50
    finally:
        win32_utils.list_desktop_windows = orig_list


def test_resolve_coordinates_screenshot_scaling():
    """Verify coordinates specified in screenshot space are scaled to physical screen pixels."""
    obs_mock = {
        "screenshot_dimensions": {"width": 1280, "height": 800},
        "scale_factors": {"scale_x": 2.0, "scale_y": 2.0}
    }
    from agent.core.vision import SCREEN_OBSERVER
    orig_obs = SCREEN_OBSERVER.latest_observation
    SCREEN_OBSERVER.latest_observation = obs_mock
    try:
        resolved, coords, err = win32_utils.resolve_coordinates({
            "start_x": 100, "start_y": 100,
            "end_x": 200, "end_y": 200,
            "coordinate_space": "screenshot"
        })
        assert resolved is True
        assert coords["start_x"] == 200 # 100 * 2.0
        assert coords["start_y"] == 200 # 100 * 2.0
        assert coords["end_x"] == 400   # 200 * 2.0
        assert coords["end_y"] == 400   # 200 * 2.0
    finally:
        SCREEN_OBSERVER.latest_observation = orig_obs


def test_global_input_serialization_concurrency():
    """Verify that concurrent input operations serialize cleanly through _GLOBAL_INPUT_LOCK."""
    execution_order = []

    def mock_action_a():
        with win32_utils._GLOBAL_INPUT_LOCK:
            execution_order.append("A_start")
            time.sleep(0.05)
            execution_order.append("A_end")

    def mock_action_b():
        with win32_utils._GLOBAL_INPUT_LOCK:
            execution_order.append("B_start")
            time.sleep(0.05)
            execution_order.append("B_end")

    t1 = threading.Thread(target=mock_action_a)
    t2 = threading.Thread(target=mock_action_b)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Assert non-interleaved atomic execution: either A starts and ends before B, or B starts and ends before A
    assert (execution_order == ["A_start", "A_end", "B_start", "B_end"]) or \
           (execution_order == ["B_start", "B_end", "A_start", "A_end"])


def test_stuck_button_release_on_error():
    """Verify that held buttons are cleared and release_all_buttons executes safely."""
    win32_utils.HELD_BUTTONS.add("left")
    win32_utils.HELD_BUTTONS.add("right")
    assert len(win32_utils.HELD_BUTTONS) == 2
    
    win32_utils.release_all_buttons()
    assert len(win32_utils.HELD_BUTTONS) == 0


def test_snap_assist_edge_rejection():
    """Verify that drags starting or ending in the top Snap Assist trigger zone (y <= 5) are rejected."""
    args = {"start_x": 500, "start_y": 2, "end_x": 500, "end_y": 300}
    is_valid, err = validate_action("mouse_drag", args)
    assert is_valid is False
    assert "Snap Assist" in err


def test_visual_verification_detects_pixel_diff():
    """Verify that verify_visual_change correctly detects modified pixels and flags success."""
    img1 = Image.new("RGB", (200, 200), color=(255, 255, 255))
    img2 = Image.new("RGB", (200, 200), color=(255, 255, 255))
    for x in range(50, 150):
        img2.putpixel((x, 100), (0, 0, 0))

    ver = verify_visual_change(img1, img2, min_changed_pixels=20)
    assert ver["verification_status"] == "verified_success"
    assert ver["change_detected"] is True
    assert ver["pixels_changed"] == 100

    # Blank/unchanged image should fail verification
    ver_blank = verify_visual_change(img1, img1, min_changed_pixels=20)
    assert ver_blank["verification_status"] == "verification_failed"
    assert ver_blank["change_detected"] is False


def test_drawing_tools_registration_and_catalog():
    """Verify all drawing tools are registered in get_all_tools catalog with proper schemas."""
    tools = get_all_tools()
    assert "draw_line" in tools
    assert "draw_polyline" in tools
    assert "draw_rectangle" in tools
    assert "draw_shape" in tools

    line_tool = tools["draw_line"]
    assert line_tool.required_scope == "computer.mouse"
    schema = line_tool.parameters
    assert "start_x" in schema["properties"]
    assert "start_y" in schema["properties"]

    shape_tool = tools["draw_shape"]
    shape_schema = shape_tool.parameters
    assert "shape_type" in shape_schema["properties"]
    assert "size" in shape_schema["properties"]


@pytest.mark.asyncio
async def test_mouse_drag_tool_structured_return():
    """Verify MouseDragTool returns input_executed and coordinates_used metadata."""
    tool = MouseDragTool()
    orig_resolve = win32_utils.resolve_coordinates
    orig_drag = win32_utils.mouse_drag
    win32_utils.resolve_coordinates = lambda args: (True, {"start_x": 200, "start_y": 200, "end_x": 300, "end_y": 200}, None)
    win32_utils.mouse_drag = lambda sx, sy, ex, ey, dur, btn: True
    try:
        res = await tool.execute({"start_x": 200, "start_y": 200, "end_x": 300, "end_y": 200})
        assert res["success"] is True
        assert res["input_executed"] is True
        assert res["coordinates_used"] == {"start_x": 200, "start_y": 200, "end_x": 300, "end_y": 200}
        assert "verification_status" in res
    finally:
        win32_utils.resolve_coordinates = orig_resolve
        win32_utils.mouse_drag = orig_drag
