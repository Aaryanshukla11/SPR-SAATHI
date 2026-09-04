import pytest
import asyncio
import subprocess
import os
import time

from agent.core import win32_utils
from agent.tools.windows import LaunchAppTool, ListWindowsTool, FocusWindowTool
from agent.tools.computer import KeyboardTypeTool, MouseMoveTool, MouseScrollTool


@pytest.mark.asyncio
async def test_real_windows_application_lifecycle_and_interaction():
    """
    Real Runtime Test:
    1. Launch real Notepad via LaunchAppTool.
    2. Verify application readiness detection with real Win32 window handles.
    3. Verify ListWindowsTool detects the real Notepad window.
    4. Verify FocusWindowTool brings Notepad to the foreground and verifies foreground state.
    5. Verify window responsiveness via Win32 IsHungAppWindow API.
    6. Verify MouseMoveTool and MouseScrollTool execute safely against real OS desktop.
    7. Terminate the launched process cleanly.
    """
    if not win32_utils.IS_WINDOWS:
        pytest.skip("Real runtime test requires Windows OS environment.")

    # 1. Launch Notepad
    launch_tool = LaunchAppTool()
    launch_res = await launch_tool.execute({"app_name": "notepad.exe"})
    assert launch_res["success"] is True, f"Launch failed with error: {launch_res.get('error')}"

    # Allow brief window appearance
    await asyncio.sleep(0.5)

    # 2. Verify ListWindowsTool sees the real Notepad window
    list_tool = ListWindowsTool()
    list_res = await list_tool.execute({})
    assert list_res["success"] is True

    notepad_window = None
    for w in list_res["windows"]:
        if "notepad" in w["process"].lower() or "notepad" in w["title"].lower():
            notepad_window = w
            break

    assert notepad_window is not None, "Real Notepad window was not found in desktop windows list."
    notepad_hwnd = notepad_window["hwnd"]
    assert notepad_hwnd > 0

    # 3. Verify responsiveness check
    responsive = win32_utils.is_window_responsive(notepad_hwnd)
    assert responsive is True, "Launched Notepad window should be responsive to Windows messages."

    # 4. Verify FocusWindowTool and foreground verification
    focus_tool = FocusWindowTool()
    focus_res = await focus_tool.execute({"process_name": "notepad.exe"})
    assert focus_res["success"] is True
    assert focus_res["target_hwnd"] == notepad_hwnd

    # 5. Verify real mouse movement and scrolling over active desktop
    move_tool = MouseMoveTool()
    move_res = await move_tool.execute({"x": 200, "y": 200, "coordinate_space": "screen"})
    assert move_res["success"] is True

    scroll_tool = MouseScrollTool()
    scroll_res = await scroll_tool.execute({"clicks": 2, "direction": "down"})
    assert scroll_res["success"] is True

    # 6. Clean up the spawned Notepad process
    try:
        win32_utils.close_window(notepad_hwnd)
        await asyncio.sleep(0.3)
        # Force terminate if still lingering
        subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
    except Exception:
        pass
