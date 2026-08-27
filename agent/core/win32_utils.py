import ctypes
import time
import sys
from typing import Dict, Any, List, Optional, Tuple

IS_WINDOWS = sys.platform == "win32"

# Constants for Input type
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

# Constants for Keyboard flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE = 0x0004

# Constants for Mouse flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000

# Track mouse buttons held down by the AI
HELD_BUTTONS = set()

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long)
    ]

# Setup structures for SendInput
if IS_WINDOWS:
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", ctypes.c_ulong),
            ("wParamL", ctypes.c_ushort),
            ("wParamH", ctypes.c_ushort)
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("ki", KEYBDINPUT),
            ("mi", MOUSEINPUT),
            ("hi", HARDWAREINPUT)
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("u", INPUT_UNION)
        ]
else:
    # Minimal mock definitions for non-Windows testing
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = []
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = []
    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong)]

# Virtual Key Mapping
VK_MAP = {
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "TAB": 0x09,
    "SPACE": 0x20,
    "BACKSPACE": 0x08,
    "BACK": 0x08,
    "ESCAPE": 0x1B,
    "DELETE": 0x2E,
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "SHIFT": 0x10,
    "ALT": 0x12,
    "WIN": 0x5B,
    "LWIN": 0x5B,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "HOME": 0x24,
    "END": 0x23,
    "PAGE_UP": 0x21,
    "PAGE_DOWN": 0x22,
    "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45, "F": 0x46, "G": 0x47, "H": 0x48, "I": 0x49,
    "J": 0x4A, "K": 0x4B, "L": 0x4C, "M": 0x4D, "N": 0x4E, "O": 0x4F, "P": 0x50, "Q": 0x51, "R": 0x52,
    "S": 0x53, "T": 0x54, "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58, "Y": 0x59, "Z": 0x5A
}

# --- Core Keyboard Injection ---

def send_input_keyboard(vk_code: int, scan_code: int, flags: int):
    if not IS_WINDOWS:
        return
    ki = KEYBDINPUT(wVk=vk_code, wScan=scan_code, dwFlags=flags, time=0, dwExtraInfo=None)
    u = INPUT_UNION(ki=ki)
    inp = INPUT(type=INPUT_KEYBOARD, u=u)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

def press_key(key_name: str):
    key = key_name.upper().strip()
    vk = VK_MAP.get(key)
    if not vk:
        raise ValueError(f"Unknown virtual key name: {key_name}")
    send_input_keyboard(vk, 0, 0)
    time.sleep(0.01)
    send_input_keyboard(vk, 0, KEYEVENTF_KEYUP)

def hotkey(keys: List[str]):
    modifiers = []
    base_keys = []
    
    for k in keys:
        k_upper = k.upper().strip()
        if k_upper in ["CTRL", "CONTROL", "SHIFT", "ALT", "WIN", "LWIN"]:
            modifiers.append(k_upper)
        else:
            base_keys.append(k_upper)
            
    # Press modifiers
    for mod in modifiers:
        vk = VK_MAP.get(mod)
        if vk:
            send_input_keyboard(vk, 0, 0)
            
    # Press & Release base keys
    for bk in base_keys:
        vk = VK_MAP.get(bk)
        if vk:
            send_input_keyboard(vk, 0, 0)
            time.sleep(0.01)
            send_input_keyboard(vk, 0, KEYEVENTF_KEYUP)
            
    # Release modifiers in reverse order
    for mod in reversed(modifiers):
        vk = VK_MAP.get(mod)
        if vk:
            send_input_keyboard(vk, 0, KEYEVENTF_KEYUP)

def type_text(text: str):
    for char in text:
        # UTF-16 code units
        code_units = char.encode('utf-16-le')
        for i in range(0, len(code_units), 2):
            val = int.from_bytes(code_units[i:i+2], byteorder='little')
            send_input_keyboard(0, val, KEYEVENTF_UNICODE)
            time.sleep(0.005)
            send_input_keyboard(0, val, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)

# --- Core Mouse and Screen State Injection ---

def get_screen_size() -> Tuple[int, int]:
    if not IS_WINDOWS:
        return 1920, 1080
    w = ctypes.windll.user32.GetSystemMetrics(0)
    h = ctypes.windll.user32.GetSystemMetrics(1)
    return w, h

def get_cursor_position() -> Tuple[int, int]:
    if not IS_WINDOWS:
        return 0, 0
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def send_mouse_event(flags: int, dx: int = 0, dy: int = 0, data: int = 0):
    if not IS_WINDOWS:
        return
    mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=None)
    u = INPUT_UNION(mi=mi)
    inp = INPUT(type=INPUT_MOUSE, u=u)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

def mouse_move(x: int, y: int, duration_ms: int = 0):
    if not IS_WINDOWS:
        return
    if duration_ms <= 0:
        ctypes.windll.user32.SetCursorPos(x, y)
    else:
        # Interpolate mouse movement smoothly
        start_x, start_y = get_cursor_position()
        steps = max(1, duration_ms // 10)  # 10ms intervals
        for i in range(1, steps + 1):
            t = i / steps
            curr_x = int(start_x + (x - start_x) * t)
            curr_y = int(start_y + (y - start_y) * t)
            ctypes.windll.user32.SetCursorPos(curr_x, curr_y)
            time.sleep(0.01)

def mouse_down(button: str = "left"):
    b = button.lower().strip()
    if b == "left":
        send_mouse_event(MOUSEEVENTF_LEFTDOWN)
        HELD_BUTTONS.add("left")
    elif b == "right":
        send_mouse_event(MOUSEEVENTF_RIGHTDOWN)
        HELD_BUTTONS.add("right")
    elif b == "middle":
        send_mouse_event(MOUSEEVENTF_MIDDLEDOWN)
        HELD_BUTTONS.add("middle")

def mouse_up(button: str = "left"):
    b = button.lower().strip()
    if b == "left":
        send_mouse_event(MOUSEEVENTF_LEFTUP)
        HELD_BUTTONS.discard("left")
    elif b == "right":
        send_mouse_event(MOUSEEVENTF_RIGHTUP)
        HELD_BUTTONS.discard("right")
    elif b == "middle":
        send_mouse_event(MOUSEEVENTF_MIDDLEUP)
        HELD_BUTTONS.discard("middle")

def mouse_click(x: int, y: int, button: str = "left", click_count: int = 1):
    mouse_move(x, y)
    time.sleep(0.05)
    for _ in range(click_count):
        mouse_down(button)
        time.sleep(0.02)
        mouse_up(button)
        if click_count > 1:
            time.sleep(0.1)

def mouse_double_click(x: int, y: int, button: str = "left"):
    mouse_click(x, y, button, click_count=2)

def mouse_drag(start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int = 200, button: str = "left"):
    mouse_move(start_x, start_y)
    time.sleep(0.1)
    mouse_down(button)
    time.sleep(0.05)
    mouse_move(end_x, end_y, duration_ms)
    time.sleep(0.05)
    mouse_up(button)

def release_all_buttons():
    # Releases any mouse button currently registered in the HELD_BUTTONS set
    for button in list(HELD_BUTTONS):
        mouse_up(button)
    HELD_BUTTONS.clear()

# --- Windows Management Injection ---

def get_active_window_details() -> Optional[Dict[str, Any]]:
    if not IS_WINDOWS:
        return {
            "title": "Mock OS - Desktop",
            "process": "explorer.exe",
            "pid": 9999,
            "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080}
        }
        
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return None
        
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value
    
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    
    rect = RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    
    process_name = "unknown"
    if pid.value:
        import psutil
        try:
            process_name = psutil.Process(pid.value).name()
        except Exception:
            pass
            
    return {
        "hwnd": hwnd,
        "title": title,
        "process": process_name,
        "pid": pid.value,
        "bounds": {
            "x": int(rect.left),
            "y": int(rect.top),
            "width": int(rect.right - rect.left),
            "height": int(rect.bottom - rect.top)
        }
    }

if IS_WINDOWS:
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
else:
    WNDENUMPROC = None

def list_desktop_windows() -> List[Dict[str, Any]]:
    if not IS_WINDOWS:
        return [
            {
                "hwnd": 1111,
                "title": "Mock OS - Desktop",
                "process": "explorer.exe",
                "pid": 9999,
                "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080}
            }
        ]
        
    windows_list = []
    
    def enum_callback(hwnd, lparam):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                
                rect = RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                
                process_name = "unknown"
                if pid.value:
                    import psutil
                    try:
                        process_name = psutil.Process(pid.value).name()
                    except Exception:
                        pass
                
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w > 0 and h > 0:
                    windows_list.append({
                        "hwnd": hwnd,
                        "title": title,
                        "process": process_name,
                        "pid": pid.value,
                        "bounds": {
                            "x": int(rect.left),
                            "y": int(rect.top),
                            "width": int(w),
                            "height": int(h)
                        }
                    })
        return True

    cb = WNDENUMPROC(enum_callback)
    ctypes.windll.user32.EnumWindows(cb, 0)
    return windows_list

def focus_window(hwnd: int) -> bool:
    if not IS_WINDOWS:
        return True
        
    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return False
        
    if ctypes.windll.user32.IsIconic(hwnd):
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    else:
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
        
    ctypes.windll.user32.BringWindowToTop(hwnd)
    
    # ALT key tap workaround to bypass OS SetForegroundWindow blocks
    send_input_keyboard(0x12, 0, 0)
    send_input_keyboard(0x12, 0, KEYEVENTF_KEYUP)
    
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    return True

def close_window(hwnd: int) -> bool:
    if not IS_WINDOWS:
        return True
        
    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return False
        
    success = ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    return bool(success)

def resolve_coordinates(arguments: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[int], Optional[str]]:
    """
    Checks if a target window is specified in the arguments.
    If so, converts x, y relative coords to absolute coords.
    Checks:
    - If window exists.
    - If window is minimized or invisible where interaction is impossible.
    - If window bounds are valid.
    Returns: (success, abs_x, abs_y, error_message)
    """
    target_window = arguments.get("target_window")
    if not target_window and "target" in arguments:
        target_obj = arguments["target"]
        if isinstance(target_obj, dict):
            target_window = target_obj.get("window")
            
    x = arguments.get("x")
    y = arguments.get("y")
    
    is_drag = "start_x" in arguments
    if is_drag:
        start_x = arguments.get("start_x")
        start_y = arguments.get("start_y")
        end_x = arguments.get("end_x")
        end_y = arguments.get("end_y")
        
    if not target_window:
        if is_drag:
            return True, None, None, None
        return True, x, y, None

    # Lookup window
    windows = list_desktop_windows()
    target_hwnd = None
    target_win = None
    
    for w in windows:
        if target_window.lower() in w["title"].lower():
            target_hwnd = w["hwnd"]
            target_win = w
            break
            
    if not target_hwnd:
        return False, None, None, f"Target window '{target_window}' not found on the desktop."
        
    # Check if window is minimized or invisible
    if IS_WINDOWS:
        if ctypes.windll.user32.IsIconic(target_hwnd):
            return False, None, None, f"Target window '{target_window}' is minimized. Cannot execute coordinate-relative inputs."
        if not ctypes.windll.user32.IsWindowVisible(target_hwnd):
            return False, None, None, f"Target window '{target_window}' is invisible."
            
    bounds = target_win["bounds"]
    if bounds["width"] <= 0 or bounds["height"] <= 0:
        return False, None, None, f"Target window '{target_window}' has invalid boundaries ({bounds['width']}x{bounds['height']})."
        
    # Convert coordinates
    if is_drag:
        abs_start_x = bounds["x"] + start_x
        abs_start_y = bounds["y"] + start_y
        abs_end_x = bounds["x"] + end_x
        abs_end_y = bounds["y"] + end_y
        
        screen_w, screen_h = get_screen_size()
        if not (0 <= abs_start_x < screen_w) or not (0 <= abs_start_y < screen_h) or \
           not (0 <= abs_end_x < screen_w) or not (0 <= abs_end_y < screen_h):
            return False, None, None, f"Converted drag coordinates (start: {abs_start_x},{abs_start_y}; end: {abs_end_x},{abs_end_y}) are outside screen boundaries."
            
        arguments["start_x"] = abs_start_x
        arguments["start_y"] = abs_start_y
        arguments["end_x"] = abs_end_x
        arguments["end_y"] = abs_end_y
        return True, None, None, None
    else:
        abs_x = bounds["x"] + x
        abs_y = bounds["y"] + y
        
        screen_w, screen_h = get_screen_size()
        if not (0 <= abs_x < screen_w) or not (0 <= abs_y < screen_h):
            return False, None, None, f"Converted coordinates ({abs_x}, {abs_y}) are outside screen boundaries."
            
        arguments["x"] = abs_x
        arguments["y"] = abs_y
        return True, abs_x, abs_y, None

