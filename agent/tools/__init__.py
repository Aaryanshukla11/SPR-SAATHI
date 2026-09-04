from typing import Dict
from .base import BaseTool
from .computer import (
    MouseMoveTool, MouseClickTool, MouseDoubleClickTool,
    MouseDownTool, MouseUpTool, MouseDragTool, MouseScrollTool,
    KeyboardTypeTool, KeyboardPressTool, KeyboardHotkeyTool
)
from .windows import LaunchAppTool, ListWindowsTool, FocusWindowTool, TakeScreenshotTool
from .filesystem import CreateFileTool, ReadFileTool
from .terminal import CmdTool, PowerShellTool
from .browser import OpenBrowserUrlTool, WebSearchTool, DownloadFileTool

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
        MouseScrollTool(),
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
        OpenBrowserUrlTool(),
        WebSearchTool(),
        DownloadFileTool()
    ]
    return {tool.name: tool for tool in tools}

