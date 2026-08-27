from typing import Dict, Any, List
import time
from .base import BaseTool
from agent.core import win32_utils

class MouseMoveTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_move"

    @property
    def description(self) -> str:
        return "Move the mouse cursor to a specific coordinate on the screen or relative to a window."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate in pixels"},
                "y": {"type": "integer", "description": "Y coordinate in pixels"},
                "duration_ms": {"type": "integer", "description": "Optional interpolation duration", "default": 0},
                "target_window": {"type": "string", "description": "Optional target window title"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        resolved, abs_x, abs_y, err = win32_utils.resolve_coordinates(arguments)
        if not resolved:
            return {"call_id": "", "success": False, "output": "", "error": err}
            
        duration = arguments.get("duration_ms", 0)
        try:
            win32_utils.mouse_move(abs_x, abs_y, duration)
            msg = f"Moved mouse cursor to ({abs_x}, {abs_y})"
            return {"call_id": "", "success": True, "output": msg, "error": None}
        except Exception as e:
            return {"call_id": "", "success": False, "output": "", "error": f"Failed to move mouse: {str(e)}"}


class MouseClickTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_click"

    @property
    def description(self) -> str:
        return "Click the mouse at specific coordinates on the screen or relative to a window."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "click_count": {"type": "integer", "default": 1},
                "target_window": {"type": "string", "description": "Optional target window title"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        resolved, abs_x, abs_y, err = win32_utils.resolve_coordinates(arguments)
        if not resolved:
            return {"call_id": "", "success": False, "output": "", "error": err}
            
        button = arguments.get("button", "left")
        count = arguments.get("click_count", 1)
        try:
            win32_utils.mouse_click(abs_x, abs_y, button, count)
            msg = f"Mouse clicked {count} times with '{button}' button at ({abs_x}, {abs_y})"
            return {"call_id": "", "success": True, "output": msg, "error": None}
        except Exception as e:
            return {"call_id": "", "success": False, "output": "", "error": f"Failed to click mouse: {str(e)}"}


class MouseDoubleClickTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_double_click"

    @property
    def description(self) -> str:
        return "Double click the mouse at specific coordinates on the screen or relative to a window."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "target_window": {"type": "string", "description": "Optional target window title"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        resolved, abs_x, abs_y, err = win32_utils.resolve_coordinates(arguments)
        if not resolved:
            return {"call_id": "", "success": False, "output": "", "error": err}
            
        button = arguments.get("button", "left")
        try:
            win32_utils.mouse_double_click(abs_x, abs_y, button)
            msg = f"Mouse double clicked with '{button}' button at ({abs_x}, {abs_y})"
            return {"call_id": "", "success": True, "output": msg, "error": None}
        except Exception as e:
            return {"call_id": "", "success": False, "output": "", "error": f"Failed double click: {str(e)}"}


class MouseDownTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_down"

    @property
    def description(self) -> str:
        return "Press down a mouse button at specific coordinates."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "target_window": {"type": "string", "description": "Optional target window title"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        resolved, abs_x, abs_y, err = win32_utils.resolve_coordinates(arguments)
        if not resolved:
            return {"call_id": "", "success": False, "output": "", "error": err}
            
        button = arguments.get("button", "left")
        try:
            win32_utils.mouse_move(abs_x, abs_y)
            time.sleep(0.02)
            win32_utils.mouse_down(button)
            msg = f"Mouse button '{button}' pressed down at ({abs_x}, {abs_y})"
            return {"call_id": "", "success": True, "output": msg, "error": None}
        except Exception as e:
            return {"call_id": "", "success": False, "output": "", "error": f"Failed mouse down: {str(e)}"}


class MouseUpTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_up"

    @property
    def description(self) -> str:
        return "Release a mouse button at specific coordinates."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "target_window": {"type": "string", "description": "Optional target window title"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        resolved, abs_x, abs_y, err = win32_utils.resolve_coordinates(arguments)
        if not resolved:
            return {"call_id": "", "success": False, "output": "", "error": err}
            
        button = arguments.get("button", "left")
        try:
            win32_utils.mouse_move(abs_x, abs_y)
            time.sleep(0.02)
            win32_utils.mouse_up(button)
            msg = f"Mouse button '{button}' released at ({abs_x}, {abs_y})"
            return {"call_id": "", "success": True, "output": msg, "error": None}
        except Exception as e:
            return {"call_id": "", "success": False, "output": "", "error": f"Failed mouse up: {str(e)}"}


class MouseDragTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_drag"

    @property
    def description(self) -> str:
        return "Drag mouse cursor from start to end coordinates."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer"},
                "start_y": {"type": "integer"},
                "end_x": {"type": "integer"},
                "end_y": {"type": "integer"},
                "duration_ms": {"type": "integer", "default": 200},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "target_window": {"type": "string", "description": "Optional target window title"}
            },
            "required": ["start_x", "start_y", "end_x", "end_y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        resolved, abs_x, abs_y, err = win32_utils.resolve_coordinates(arguments)
        if not resolved:
            return {"call_id": "", "success": False, "output": "", "error": err}
            
        start_x = arguments.get("start_x")
        start_y = arguments.get("start_y")
        end_x = arguments.get("end_x")
        end_y = arguments.get("end_y")
        duration = arguments.get("duration_ms", 200)
        button = arguments.get("button", "left")
        try:
            win32_utils.mouse_drag(start_x, start_y, end_x, end_y, duration, button)
            msg = f"Mouse dragged from ({start_x}, {start_y}) to ({end_x}, {end_y}) using '{button}' button"
            return {"call_id": "", "success": True, "output": msg, "error": None}
        except Exception as e:
            return {"call_id": "", "success": False, "output": "", "error": f"Failed mouse drag: {str(e)}"}


class KeyboardTypeTool(BaseTool):
    @property
    def name(self) -> str:
        return "keyboard_type"

    @property
    def description(self) -> str:
        return "Type a string of text on the keyboard into the currently active window."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to type"}
            },
            "required": ["text"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        text = arguments.get("text", "")
        try:
            win32_utils.type_text(text)
            msg = f"Typed text: '{text}'"
            return {
                "call_id": "",
                "success": True,
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": f"Failed to type keyboard text: {str(e)}"
            }


class KeyboardPressTool(BaseTool):
    @property
    def name(self) -> str:
        return "keyboard_press"

    @property
    def description(self) -> str:
        return "Press and release a single key (e.g. ENTER, TAB, BACKSPACE)."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name (e.g. ENTER, TAB, BACKSPACE)"}
            },
            "required": ["key"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        key = arguments.get("key", "").strip()
        try:
            win32_utils.press_key(key)
            msg = f"Pressed key: '{key}'"
            return {
                "call_id": "",
                "success": True,
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": f"Failed to press key '{key}': {str(e)}"
            }


class KeyboardHotkeyTool(BaseTool):
    @property
    def name(self) -> str:
        return "keyboard_hotkey"

    @property
    def description(self) -> str:
        return "Execute a key combination (e.g. CTRL+A, CTRL+S)."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keys forming the hotkey (e.g. ['CTRL', 'S'])"
                }
            },
            "required": ["keys"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        keys = arguments.get("keys", [])
        try:
            win32_utils.hotkey(keys)
            msg = f"Executed hotkey: {keys}"
            return {
                "call_id": "",
                "success": True,
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": f"Failed to execute hotkey combination {keys}: {str(e)}"
            }
