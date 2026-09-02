from typing import Dict
from .base import BaseTool
from .computer import (
    MouseMoveTool, MouseClickTool, MouseDoubleClickTool,
    MouseDownTool, MouseUpTool, MouseDragTool,
    KeyboardTypeTool, KeyboardPressTool, KeyboardHotkeyTool
)
from .windows import LaunchAppTool, ListWindowsTool, FocusWindowTool, TakeScreenshotTool
from .filesystem import CreateFileTool, ReadFileTool
from .terminal import CmdTool, PowerShellTool
from .browser import OpenBrowserUrlTool

from .drawing import (
    DrawLineTool, DrawPolylineTool, DrawRectangleTool, DrawShapeTool
)

def get_all_tools() -> Dict[str, BaseTool]:
    tools = [
        MouseMoveTool(),
        MouseClickTool(),
        MouseDoubleClickTool(),
        MouseDownTool(),
        MouseUpTool(),
        MouseDragTool(),
        DrawLineTool(),
        DrawPolylineTool(),
        DrawRectangleTool(),
        DrawShapeTool(),
        KeyboardTypeTool(),
        KeyboardPressTool(),
        KeyboardHotkeyTool(),
        LaunchAppTool(),
        ListWindowsTool(),
        FocusWindowTool(),
        TakeScreenshotTool(),
        CreateFileTool(),
        ReadFileTool(),
        CmdTool(),
        PowerShellTool(),
        OpenBrowserUrlTool()
    ]
    return {tool.name: tool for tool in tools}

