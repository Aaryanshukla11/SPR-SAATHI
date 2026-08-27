from typing import Dict
from .base import BaseTool
from .computer import (
    MouseMoveTool, MouseClickTool, MouseDoubleClickTool,
    MouseDownTool, MouseUpTool, MouseDragTool,
    KeyboardTypeTool, KeyboardPressTool, KeyboardHotkeyTool
)
from .windows import LaunchAppTool, ListWindowsTool, FocusWindowTool
from .filesystem import CreateFileTool, ReadFileTool
from .terminal import CmdTool, PowerShellTool
from .browser import OpenBrowserUrlTool

def get_all_tools() -> Dict[str, BaseTool]:
    tools = [
        MouseMoveTool(),
        MouseClickTool(),
        MouseDoubleClickTool(),
        MouseDownTool(),
        MouseUpTool(),
        MouseDragTool(),
        KeyboardTypeTool(),
        KeyboardPressTool(),
        KeyboardHotkeyTool(),
        LaunchAppTool(),
        ListWindowsTool(),
        FocusWindowTool(),
        CreateFileTool(),
        ReadFileTool(),
        CmdTool(),
        PowerShellTool(),
        OpenBrowserUrlTool()
    ]
    return {tool.name: tool for tool in tools}

