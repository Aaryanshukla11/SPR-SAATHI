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
        return "Move the mouse cursor to a specific coordinate on the screen, window, or canvas (does not press buttons; for drawing or dragging use mouse_drag)."

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
                "target_window": {"type": "string", "description": "Optional target window title or process name"},
                "coordinate_space": {"type": "string", "enum": ["screen", "window", "content"], "default": "content", "description": "Coordinate reference space"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        win_before = win32_utils.get_active_window_details()
        resolved, coords, err = win32_utils.resolve_coordinates(arguments)
        if not resolved or not coords:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": None,
                "target_window_before": win_before,
                "target_window_after": win_before,
                "verification_status": "verification_failed",
                "output": "",
                "error": err
            }
            
        abs_x = coords["x"]
        abs_y = coords["y"]
        duration = arguments.get("duration_ms", 0)
        try:
            win32_utils.mouse_move(abs_x, abs_y, duration)
            win_after = win32_utils.get_active_window_details()
            msg = f"Moved mouse cursor to ({abs_x}, {abs_y})"
            return {
                "call_id": "",
                "success": True,
                "input_executed": True,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win_after,
                "verification_status": "verified_success",
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win32_utils.get_active_window_details(),
                "verification_status": "verification_failed",
                "output": "",
                "error": f"Failed to move mouse: {str(e)}"
            }


class MouseClickTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_click"

    @property
    def description(self) -> str:
        return "Click the mouse at specific coordinates on the screen, window, or canvas."

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
                "target_window": {"type": "string", "description": "Optional target window title"},
                "coordinate_space": {"type": "string", "enum": ["screen", "window", "content"], "default": "content"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        win_before = win32_utils.get_active_window_details()
        resolved, coords, err = win32_utils.resolve_coordinates(arguments)
        if not resolved or not coords:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": None,
                "target_window_before": win_before,
                "target_window_after": win_before,
                "verification_status": "verification_failed",
                "output": "",
                "error": err
            }
            
        abs_x = coords["x"]
        abs_y = coords["y"]
        button = arguments.get("button", "left")
        count = arguments.get("click_count", 1)
        try:
            win32_utils.mouse_click(abs_x, abs_y, button, count)
            win_after = win32_utils.get_active_window_details()
            
            # Check for Snap Assist or unwanted focus switch
            if win_after and "snap assist" in (win_after.get("title") or "").lower():
                return {
                    "call_id": "",
                    "success": False,
                    "input_executed": True,
                    "coordinates_used": {"x": abs_x, "y": abs_y},
                    "target_window_before": win_before,
                    "target_window_after": win_after,
                    "verification_status": "verification_failed",
                    "output": "",
                    "error": "Click operation accidentally triggered Windows Snap Assist."
                }

            msg = f"Mouse clicked {count} times with '{button}' button at ({abs_x}, {abs_y})"
            return {
                "call_id": "",
                "success": True,
                "input_executed": True,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win_after,
                "verification_status": "verified_success",
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win32_utils.get_active_window_details(),
                "verification_status": "verification_failed",
                "output": "",
                "error": f"Failed to click mouse: {str(e)}"
            }


class MouseDoubleClickTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_double_click"

    @property
    def description(self) -> str:
        return "Double click the mouse at specific coordinates on the screen, window, or canvas."

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
                "target_window": {"type": "string", "description": "Optional target window title"},
                "coordinate_space": {"type": "string", "enum": ["screen", "window", "content"], "default": "content"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        win_before = win32_utils.get_active_window_details()
        resolved, coords, err = win32_utils.resolve_coordinates(arguments)
        if not resolved or not coords:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": None,
                "target_window_before": win_before,
                "target_window_after": win_before,
                "verification_status": "verification_failed",
                "output": "",
                "error": err
            }
            
        abs_x = coords["x"]
        abs_y = coords["y"]
        button = arguments.get("button", "left")
        try:
            win32_utils.mouse_double_click(abs_x, abs_y, button)
            win_after = win32_utils.get_active_window_details()
            msg = f"Mouse double clicked with '{button}' button at ({abs_x}, {abs_y})"
            return {
                "call_id": "",
                "success": True,
                "input_executed": True,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win_after,
                "verification_status": "verified_success",
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win32_utils.get_active_window_details(),
                "verification_status": "verification_failed",
                "output": "",
                "error": f"Failed double click: {str(e)}"
            }


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
                "target_window": {"type": "string", "description": "Optional target window title"},
                "coordinate_space": {"type": "string", "enum": ["screen", "window", "content"], "default": "content"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        win_before = win32_utils.get_active_window_details()
        resolved, coords, err = win32_utils.resolve_coordinates(arguments)
        if not resolved or not coords:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": None,
                "target_window_before": win_before,
                "target_window_after": win_before,
                "verification_status": "verification_failed",
                "output": "",
                "error": err
            }
            
        abs_x = coords["x"]
        abs_y = coords["y"]
        button = arguments.get("button", "left")
        try:
            win32_utils.mouse_move(abs_x, abs_y)
            time.sleep(0.02)
            win32_utils.mouse_down(button)
            msg = f"Mouse button '{button}' pressed down at ({abs_x}, {abs_y})"
            return {
                "call_id": "",
                "success": True,
                "input_executed": True,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win32_utils.get_active_window_details(),
                "verification_status": "verified_success",
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win32_utils.get_active_window_details(),
                "verification_status": "verification_failed",
                "output": "",
                "error": f"Failed mouse down: {str(e)}"
            }


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
                "target_window": {"type": "string", "description": "Optional target window title"},
                "coordinate_space": {"type": "string", "enum": ["screen", "window", "content"], "default": "content"}
            },
            "required": ["x", "y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        win_before = win32_utils.get_active_window_details()
        resolved, coords, err = win32_utils.resolve_coordinates(arguments)
        if not resolved or not coords:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": None,
                "target_window_before": win_before,
                "target_window_after": win_before,
                "verification_status": "verification_failed",
                "output": "",
                "error": err
            }
            
        abs_x = coords["x"]
        abs_y = coords["y"]
        button = arguments.get("button", "left")
        try:
            win32_utils.mouse_move(abs_x, abs_y)
            time.sleep(0.02)
            win32_utils.mouse_up(button)
            msg = f"Mouse button '{button}' released at ({abs_x}, {abs_y})"
            return {
                "call_id": "",
                "success": True,
                "input_executed": True,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win32_utils.get_active_window_details(),
                "verification_status": "verified_success",
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": {"x": abs_x, "y": abs_y},
                "target_window_before": win_before,
                "target_window_after": win32_utils.get_active_window_details(),
                "verification_status": "verification_failed",
                "output": "",
                "error": f"Failed mouse up: {str(e)}"
            }


class MouseDragTool(BaseTool):
    @property
    def name(self) -> str:
        return "mouse_drag"

    @property
    def description(self) -> str:
        return "Drag mouse cursor from start to end coordinates while holding down a mouse button (essential for drawing lines, shapes, dragging objects, sliders, and canvas strokes)."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer", "description": "Start X coordinate"},
                "start_y": {"type": "integer", "description": "Start Y coordinate"},
                "end_x": {"type": "integer", "description": "End X coordinate"},
                "end_y": {"type": "integer", "description": "End Y coordinate"},
                "duration_ms": {"type": "integer", "default": 250, "description": "Duration of drag interpolation in milliseconds"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "target_window": {"type": "string", "description": "Optional target window title or process name"},
                "coordinate_space": {"type": "string", "enum": ["screen", "window", "content"], "default": "content", "description": "Coordinate space: screen, window, or content/canvas"}
            },
            "required": ["start_x", "start_y", "end_x", "end_y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from agent.core.vision import SCREEN_OBSERVER, verify_visual_change
        win_before = win32_utils.get_active_window_details()
        resolved, coords, err = win32_utils.resolve_coordinates(arguments)
        if not resolved or not coords:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": None,
                "target_window_before": win_before,
                "target_window_after": win_before,
                "verification_status": "verification_failed",
                "output": "",
                "error": err
            }
            
        start_x = coords["start_x"]
        start_y = coords["start_y"]
        end_x = coords["end_x"]
        end_y = coords["end_y"]
        duration = arguments.get("duration_ms", 250)
        button = arguments.get("button", "left")

        # Capture visual snapshot before drag if observer is active
        img_before = None
        crop_bbox = (
            min(start_x, end_x) - 40,
            min(start_y, end_y) - 40,
            max(start_x, end_x) + 40,
            max(start_y, end_y) + 40
        )
        try:
            img_before = SCREEN_OBSERVER.capture_image()
        except Exception:
            pass

        try:
            win32_utils.mouse_drag(start_x, start_y, end_x, end_y, duration, button)
            time.sleep(0.05)
            win_after = win32_utils.get_active_window_details()

            # Check if focus unexpectedly changed to Snap Assist
            if win_after and "snap assist" in (win_after.get("title") or "").lower():
                return {
                    "call_id": "",
                    "success": False,
                    "input_executed": True,
                    "coordinates_used": {"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
                    "target_window_before": win_before,
                    "target_window_after": win_after,
                    "verification_status": "verification_failed",
                    "output": "",
                    "error": "Mouse drag accidentally triggered Windows Snap Assist. Action aborted to protect desktop state."
                }

            # Visual verification of actual pixel changes
            visual_ver = {"verification_status": "execution_success_but_unverified", "change_detected": False}
            if img_before is not None:
                try:
                    img_after = SCREEN_OBSERVER.capture_image()
                    visual_ver = verify_visual_change(img_before, img_after, region_bbox=crop_bbox)
                except Exception:
                    pass

            msg = f"Mouse dragged from ({start_x}, {start_y}) to ({end_x}, {end_y}) using '{button}' button"
            return {
                "call_id": "",
                "success": True,
                "input_executed": True,
                "coordinates_used": {"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
                "target_window_before": win_before,
                "target_window_after": win_after,
                "visual_verification": visual_ver,
                "verification_status": visual_ver.get("verification_status", "execution_success_but_unverified"),
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "input_executed": False,
                "coordinates_used": {"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
                "target_window_before": win_before,
                "target_window_after": win32_utils.get_active_window_details(),
                "verification_status": "verification_failed",
                "output": "",
                "error": f"Failed mouse drag: {str(e)}"
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
        return "keyboard"

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
        call_id = arguments.get("call_id", "")
        from agent.core.keyboard_trace import KEYBOARD_TRACER
        KEYBOARD_TRACER.record_tool_call(call_id, text)
        try:
            win32_utils.type_text(text, call_id=call_id)
            msg = f"Typed text: '{text}'"
            return {
                "call_id": call_id,
                "success": True,
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": call_id,
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
