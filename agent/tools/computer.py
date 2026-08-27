from typing import Dict, Any, List
from .base import BaseTool
from agent.core import win32_utils

class MouseMoveTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_move"

    @property
    def description(self) -> str:
        return "Move the mouse cursor to a specific (x, y) coordinate on the screen."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate in pixels"},
                "y": {"type": "integer", "description": "Y coordinate in pixels"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        x = arguments.get("x")
        y = arguments.get("y")
        msg = f"Moving mouse cursor to (x={x}, y={y}) (placeholder in Phase 1)"
        print(msg)
        return {
            "call_id": "",
            "success": True,
            "output": msg,
            "error": None
        }


class MouseClickTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_click"

    @property
    def description(self) -> str:
        return "Click the mouse at the current position or optional coordinates."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "double": {"type": "boolean", "default": False}
            }
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        button = arguments.get("button", "left")
        double = arguments.get("double", False)
        click_type = "double click" if double else "click"
        msg = f"Performing mouse {click_type} with {button} button (placeholder in Phase 1)"
        print(msg)
        return {
            "call_id": "",
            "success": True,
            "output": msg,
            "error": None
        }


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
        if not text:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": "Text to type cannot be empty."
            }
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
        if not key:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": "Key name cannot be empty."
            }
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
        if not keys:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": "Hotkey keys list cannot be empty."
            }
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
