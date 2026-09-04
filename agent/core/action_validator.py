from typing import Dict, Any, Tuple, List, Optional
from agent.core import win32_utils

def validate_action(action_name: str, arguments: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validates action parameters before execution.
    Returns (is_valid, error_message).
    """
    computer_actions = {
        "mouse_move",
        "mouse_click",
        "mouse_double_click",
        "mouse_down",
        "mouse_up",
        "mouse_drag",
        "mouse_scroll",
        "draw_line",
        "draw_polyline",
        "draw_rectangle",
        "draw_shape",
        "keyboard_type",
        "keyboard_press",
        "keyboard_hotkey"
    }

    if action_name not in computer_actions:
        # Non-computer actions (e.g. launch_app, focus_window) are valid and bypass coordinate checks
        return True, None

    # Fetch screen dimensions for boundary checking of absolute coordinates
    screen_w, screen_h = win32_utils.get_screen_size()
    has_target = "target_window" in arguments or "target" in arguments

    def validate_coords(x: Any, y: Any, label_x: str, label_y: str) -> Optional[str]:
        if not isinstance(x, int) or not isinstance(y, int):
            return f"Coordinates {label_x} and {label_y} must be integers."
        # If no window target is specified, validate absolute screen boundaries
        if not has_target:
            if not (0 <= x < screen_w):
                return f"Coordinate {label_x}={x} is outside screen width bounds (0 to {screen_w - 1})."
            if not (0 <= y < screen_h):
                return f"Coordinate {label_y}={y} is outside screen height bounds (0 to {screen_h - 1})."
        return None

    # MOUSE ACTIONS
    if action_name == "mouse_move":
        x = arguments.get("x")
        y = arguments.get("y")
        duration = arguments.get("duration_ms", 0)
        
        err = validate_coords(x, y, "x", "y")
        if err: return False, err
        
        if not isinstance(duration, int) or duration < 0 or duration > 10000:
            return False, f"Duration must be an integer between 0 and 10000 ms."

    elif action_name in ["mouse_click", "mouse_double_click", "mouse_down", "mouse_up"]:
        x = arguments.get("x")
        y = arguments.get("y")
        button = arguments.get("button", "left")
        
        err = validate_coords(x, y, "x", "y")
        if err: return False, err
        
        if str(button).lower().strip() not in ["left", "right", "middle"]:
            return False, f"Unsupported mouse button: '{button}'. Must be 'left', 'right', or 'middle'."
            
        if action_name == "mouse_click":
            count = arguments.get("click_count", 1)
            if not isinstance(count, int) or count < 1 or count > 5:
                return False, f"Click count must be an integer between 1 and 5."

    elif action_name == "mouse_drag":
        start_x = arguments.get("start_x")
        start_y = arguments.get("start_y")
        end_x = arguments.get("end_x")
        end_y = arguments.get("end_y")
        duration = arguments.get("duration_ms", 250)
        button = arguments.get("button", "left")
        
        err = validate_coords(start_x, start_y, "start_x", "start_y")
        if err: return False, err
        err = validate_coords(end_x, end_y, "end_x", "end_y")
        if err: return False, err
        
        if not has_target:
            # Prevent dragging near the very top of the monitor where Windows Snap Assist / Window tiling triggers
            if start_y <= 5 or end_y <= 5:
                return False, "Drag coordinates touch the top screen edge (y <= 5) which triggers Windows Snap Assist."
        
        if str(button).lower().strip() not in ["left", "right", "middle"]:
            return False, f"Unsupported mouse button: '{button}'. Must be 'left', 'right', or 'middle'."
            
        if not isinstance(duration, int) or duration < 0 or duration > 10000:
            return False, f"Drag duration must be an integer between 0 and 10000 ms."

    elif action_name == "mouse_scroll":
        clicks = arguments.get("clicks", 1)
        direction = arguments.get("direction", "down")
        if not isinstance(clicks, int) or clicks < -100 or clicks > 100:
            return False, "Clicks must be an integer between -100 and 100."
        if str(direction).lower().strip() not in ["up", "down", "left", "right"]:
            return False, f"Unsupported scroll direction: '{direction}'. Must be 'up', 'down', 'left', or 'right'."
        if "x" in arguments and "y" in arguments:
            x = arguments.get("x")
            y = arguments.get("y")
            err = validate_coords(x, y, "x", "y")
            if err: return False, err

    # KEYBOARD ACTIONS
    elif action_name == "keyboard_type":
        text = arguments.get("text")
        if not isinstance(text, str) or not text:
            return False, "Typing text payload must be a non-empty string."

    elif action_name == "keyboard_press":
        key = arguments.get("key")
        if not isinstance(key, str) or not key.strip():
            return False, "Press key payload must be a non-empty string."
        key_norm = key.upper().strip()
        if key_norm not in win32_utils.VK_MAP:
            return False, f"Unrecognized keyboard key name: '{key}'."

    elif action_name == "keyboard_hotkey":
        keys = arguments.get("keys")
        if not isinstance(keys, list) or not keys:
            return False, "Hotkey keys must be a non-empty list of key names."
        for k in keys:
            if not isinstance(k, str) or k.upper().strip() not in win32_utils.VK_MAP:
                return False, f"Unrecognized keyboard key name in hotkey: '{k}'."

    return True, None
