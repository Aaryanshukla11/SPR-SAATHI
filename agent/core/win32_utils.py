import ctypes
import time
import sys
import threading
import math
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("agent.core.win32_utils")

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    try:
        # Enable Per-Monitor V2 DPI Awareness for exact hardware pixel mapping
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

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
            ("dwExtraInfo", ctypes.c_size_t)
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
            ("dwExtraInfo", ctypes.c_size_t)
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

    ctypes.windll.kernel32.GlobalAlloc.restype = ctypes.c_void_p
    ctypes.windll.kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    ctypes.windll.kernel32.GlobalLock.restype = ctypes.c_void_p
    ctypes.windll.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    ctypes.windll.kernel32.GlobalUnlock.restype = ctypes.c_bool
    ctypes.windll.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    ctypes.windll.kernel32.GlobalFree.restype = ctypes.c_void_p
    ctypes.windll.kernel32.GlobalFree.argtypes = [ctypes.c_void_p]

    ctypes.windll.user32.OpenClipboard.restype = ctypes.c_bool
    ctypes.windll.user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    ctypes.windll.user32.CloseClipboard.restype = ctypes.c_bool
    ctypes.windll.user32.CloseClipboard.argtypes = []
    ctypes.windll.user32.EmptyClipboard.restype = ctypes.c_bool
    ctypes.windll.user32.EmptyClipboard.argtypes = []
    ctypes.windll.user32.IsClipboardFormatAvailable.restype = ctypes.c_bool
    ctypes.windll.user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    ctypes.windll.user32.GetClipboardData.restype = ctypes.c_void_p
    ctypes.windll.user32.GetClipboardData.argtypes = [ctypes.c_uint]
    ctypes.windll.user32.SetClipboardData.restype = ctypes.c_void_p
    ctypes.windll.user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

    ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
    ctypes.windll.user32.GetForegroundWindow.argtypes = []
    ctypes.windll.user32.SetForegroundWindow.restype = ctypes.c_bool
    ctypes.windll.user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    ctypes.windll.user32.IsWindow.restype = ctypes.c_bool
    ctypes.windll.user32.IsWindow.argtypes = [ctypes.c_void_p]
    ctypes.windll.user32.IsWindowVisible.restype = ctypes.c_bool
    ctypes.windll.user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    ctypes.windll.user32.IsIconic.restype = ctypes.c_bool
    ctypes.windll.user32.IsIconic.argtypes = [ctypes.c_void_p]

    ctypes.windll.user32.SendInput.restype = ctypes.c_uint
    ctypes.windll.user32.SendInput.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]
    ctypes.windll.user32.MapVirtualKeyW.restype = ctypes.c_uint
    ctypes.windll.user32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
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
    "CTRL": 0x11,     # VK_CONTROL
    "CONTROL": 0x11,  # VK_CONTROL
    "LCTRL": 0xA2,    # VK_LCONTROL
    "RCTRL": 0xA3,    # VK_RCONTROL
    "SHIFT": 0x10,    # VK_SHIFT
    "LSHIFT": 0xA0,   # VK_LSHIFT
    "RSHIFT": 0xA1,   # VK_RSHIFT
    "ALT": 0x12,      # VK_MENU
    "LALT": 0xA4,     # VK_LMENU
    "RALT": 0xA5,     # VK_RMENU
    "WIN": 0x5B,      # VK_LWIN
    "LWIN": 0x5B,     # VK_LWIN
    "RWIN": 0x5C,     # VK_RWIN
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

# Unified thread-level global input serialization lock protecting all Windows mouse and keyboard operations
_GLOBAL_INPUT_LOCK = threading.RLock()
_KEYBOARD_LOCK = _GLOBAL_INPUT_LOCK

def release_modifier_keys():
    """Ensures any lingering modifier keys (Ctrl, Shift, Alt, Win) are physically and virtually released."""
    if not IS_WINDOWS:
        return
    modifiers_vk = [0x11, 0x10, 0x12, 0x5B, 0x5C] # VK_CONTROL, VK_SHIFT, VK_MENU, VK_LWIN, VK_RWIN
    for vk in modifiers_vk:
        state = ctypes.windll.user32.GetAsyncKeyState(vk)
        if state & 0x8000:
            scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
            ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            u = INPUT_UNION(ki=ki)
            inp = INPUT(type=INPUT_KEYBOARD, u=u)
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

def send_input_keyboard(vk_code: int, scan_code: int, flags: int):
    if not IS_WINDOWS:
        return
    # If not a Unicode packet event and scan_code is 0, compute hardware scan code
    if (flags & KEYEVENTF_UNICODE) == 0 and scan_code == 0 and vk_code != 0:
        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk_code, 0)
        # Fallback for virtual keys that MapVirtualKeyW might return 0 for
        if scan_code == 0:
            if vk_code in (0x11, 0xA2, 0xA3): # VK_CONTROL, VK_LCONTROL, VK_RCONTROL
                scan_code = 0x1D
            elif vk_code in (0x10, 0xA0, 0xA1): # VK_SHIFT, VK_LSHIFT, VK_RSHIFT
                scan_code = 0x2A
            elif vk_code in (0x12, 0xA4, 0xA5): # VK_MENU, VK_LMENU, VK_RMENU
                scan_code = 0x38
            elif vk_code == 0x56: # VK_V
                scan_code = 0x2F
            elif vk_code == 0x41: # VK_A
                scan_code = 0x1E
            elif vk_code == 0x43: # VK_C
                scan_code = 0x2E
        
    with _KEYBOARD_LOCK:
        ki = KEYBDINPUT(wVk=vk_code, wScan=scan_code, dwFlags=flags, time=0, dwExtraInfo=0)
        u = INPUT_UNION(ki=ki)
        inp = INPUT(type=INPUT_KEYBOARD, u=u)
        sent = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        if sent == 0:
            # Fallback to keybd_event if SendInput is blocked by UIPI or session isolation
            ctypes.windll.user32.keybd_event(vk_code, scan_code, flags, 0)

def press_key(key_name: str):
    key = key_name.upper().strip()
    vk = VK_MAP.get(key)
    if not vk:
        raise ValueError(f"Unknown virtual key name: {key_name}")
    with _KEYBOARD_LOCK:
        release_modifier_keys()
        send_input_keyboard(vk, 0, 0)
        time.sleep(0.02)
        send_input_keyboard(vk, 0, KEYEVENTF_KEYUP)
        time.sleep(0.02)

def hotkey(keys: List[str]):
    modifiers = []
    base_keys = []
    
    for k in keys:
        k_upper = k.upper().strip()
        if k_upper in ["CTRL", "CONTROL", "LCTRL", "RCTRL", "SHIFT", "LSHIFT", "RSHIFT", "ALT", "LALT", "RALT", "WIN", "LWIN", "RWIN"]:
            modifiers.append(k_upper)
        else:
            base_keys.append(k_upper)
            
    with _KEYBOARD_LOCK:
        release_modifier_keys()
        # Press modifiers
        for mod in modifiers:
            vk = VK_MAP.get(mod)
            if vk:
                send_input_keyboard(vk, 0, 0)
                
        if modifiers:
            time.sleep(0.025)
                
        # Press & Release base keys
        for bk in base_keys:
            vk = VK_MAP.get(bk)
            if vk:
                send_input_keyboard(vk, 0, 0)
                time.sleep(0.025)
                send_input_keyboard(vk, 0, KEYEVENTF_KEYUP)
                
        if modifiers:
            time.sleep(0.025)
            
        # Release modifiers in reverse order
        for mod in reversed(modifiers):
            vk = VK_MAP.get(mod)
            if vk:
                send_input_keyboard(vk, 0, KEYEVENTF_KEYUP)
        time.sleep(0.02)

def get_clipboard_text() -> Optional[str]:
    """
    Safely retrieves Unicode text currently on the Windows clipboard.
    Returns None if clipboard is empty, holds non-text data, or cannot be opened.
    """
    if not IS_WINDOWS:
        return None
    CF_UNICODETEXT = 13
    for _ in range(25):
        if ctypes.windll.user32.OpenClipboard(None):
            try:
                if not ctypes.windll.user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                    return None
                h_data = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
                if not h_data:
                    return None
                p_data = ctypes.windll.kernel32.GlobalLock(h_data)
                if p_data:
                    try:
                        text = ctypes.wstring_at(p_data)
                        return text
                    finally:
                        ctypes.windll.kernel32.GlobalUnlock(h_data)
            finally:
                ctypes.windll.user32.CloseClipboard()
            return None
        time.sleep(0.015)
    return None

def set_clipboard_text(text: str) -> bool:
    """Sets Unicode text onto the Windows clipboard using 64-bit Win32 GlobalAlloc/SetClipboardData."""
    if not IS_WINDOWS:
        return False
    CF_UNICODETEXT = 13
    raw_bytes = text.encode("utf-16-le") + b"\x00\x00"
    for _ in range(30):
        if ctypes.windll.user32.OpenClipboard(None):
            try:
                ctypes.windll.user32.EmptyClipboard()
                h = ctypes.windll.kernel32.GlobalAlloc(0x0042, len(raw_bytes))  # GMEM_MOVEABLE | GMEM_ZEROINIT
                if h:
                    p = ctypes.windll.kernel32.GlobalLock(h)
                    if p:
                        ctypes.memmove(p, raw_bytes, len(raw_bytes))
                        ctypes.windll.kernel32.GlobalUnlock(h)
                        res = ctypes.windll.user32.SetClipboardData(CF_UNICODETEXT, h)
                        if res:
                            return True
                        else:
                            ctypes.windll.kernel32.GlobalFree(h)
            finally:
                ctypes.windll.user32.CloseClipboard()
        time.sleep(0.02)
    return False

def type_text(text: str, chunk_size: int = 1, call_id: str = "", target_window_hwnd: Optional[int] = None):
    """
    Production-quality serialized text injection for Windows applications:
    1. Acquires _KEYBOARD_LOCK to guarantee single serialized input pipeline.
    2. Releases any stuck modifier keys.
    3. Safely saves previous clipboard contents.
    4. Places requested Unicode text onto clipboard.
    5. Verifies target window focus and restores focus if needed.
    6. Injects exactly one Ctrl+V keystroke combination.
    7. Waits for application to process paste.
    8. Restores previous clipboard contents where possible.
    9. Records comprehensive execution trace.
    """
    if not IS_WINDOWS or not text:
        return

    start_time = time.time()
    with _KEYBOARD_LOCK:
        from agent.core.keyboard_trace import KEYBOARD_TRACER
        KEYBOARD_TRACER.record_type_text_start(call_id, text, chunk_size, typing_path="win32_clipboard_paste")
        
        normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
        
        # 1. Release lingering modifier keys
        release_modifier_keys()
        
        # 2. Save current clipboard contents
        prev_clipboard = get_clipboard_text()
        
        # 3. Place requested text onto clipboard
        clip_set = set_clipboard_text(normalized_text)
        if not clip_set:
            raise RuntimeError("Failed to set text onto Windows clipboard after multiple attempts.")
            
        # 4. Verify target window focus
        target_hwnd = target_window_hwnd
        if not target_hwnd:
            target_hwnd = ctypes.windll.user32.GetForegroundWindow()
            
        if target_hwnd and ctypes.windll.user32.IsWindow(target_hwnd):
            if ctypes.windll.user32.GetForegroundWindow() != target_hwnd or ctypes.windll.user32.IsIconic(target_hwnd):
                focus_window(target_hwnd)
                time.sleep(0.05)
                
        # 5. Execute exactly one Ctrl+V operation
        send_input_keyboard(VK_MAP["CTRL"], 0x1D, 0)
        time.sleep(0.025)
        send_input_keyboard(VK_MAP["V"], 0x2F, 0)
        time.sleep(0.025)
        send_input_keyboard(VK_MAP["V"], 0x2F, KEYEVENTF_KEYUP)
        time.sleep(0.025)
        send_input_keyboard(VK_MAP["CTRL"], 0x1D, KEYEVENTF_KEYUP)
        
        # 6. Wait for the target application to finish consuming the paste message
        # Give sufficient time for application message queue and clipboard ingestion
        wait_duration = 0.45 if len(normalized_text) > 500 else 0.35
        time.sleep(wait_duration)
        
        # 7. Restore previous clipboard contents if any existed
        clipboard_restored = False
        if prev_clipboard is not None and prev_clipboard != normalized_text:
            clipboard_restored = set_clipboard_text(prev_clipboard)
            
        duration_ms = (time.time() - start_time) * 1000
        
        # Fetch target window title for trace
        target_title = None
        if target_hwnd:
            length = ctypes.windll.user32.GetWindowTextLengthW(target_hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(target_hwnd, buf, length + 1)
                target_title = buf.value
                
        # 8. Record execution trace
        KEYBOARD_TRACER.record_type_text_completed(
            call_id=call_id,
            text=normalized_text,
            typing_path="win32_clipboard_paste",
            target_hwnd=target_hwnd,
            target_title=target_title,
            clipboard_restored=clipboard_restored,
            duration_ms=duration_ms,
            retried=False
        )

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
    with _GLOBAL_INPUT_LOCK:
        mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=0)
        u = INPUT_UNION(mi=mi)
        inp = INPUT(type=INPUT_MOUSE, u=u)
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

def send_mouse_move_absolute(x: int, y: int):
    if not IS_WINDOWS:
        return
    screen_w, screen_h = get_screen_size()
    norm_x = int((x * 65535) / (screen_w - 1)) if screen_w > 1 else 0
    norm_y = int((y * 65535) / (screen_h - 1)) if screen_h > 1 else 0
    send_mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=norm_x, dy=norm_y)

def mouse_move(x: int, y: int, duration_ms: int = 0):
    if not IS_WINDOWS:
        return
    with _GLOBAL_INPUT_LOCK:
        if duration_ms <= 0:
            if HELD_BUTTONS:
                send_mouse_move_absolute(x, y)
            else:
                ctypes.windll.user32.SetCursorPos(x, y)
                send_mouse_move_absolute(x, y)
        else:
            # Interpolate mouse movement smoothly
            start_x, start_y = get_cursor_position()
            dist = math.hypot(x - start_x, y - start_y)
            steps = max(1, min(60, int(dist / 8)))
            for i in range(1, steps + 1):
                t = i / steps
                curr_x = int(start_x + (x - start_x) * t)
                curr_y = int(start_y + (y - start_y) * t)
                if HELD_BUTTONS:
                    send_mouse_move_absolute(curr_x, curr_y)
                else:
                    ctypes.windll.user32.SetCursorPos(curr_x, curr_y)
                    send_mouse_move_absolute(curr_x, curr_y)
                time.sleep(0.01)

def mouse_down(button: str = "left"):
    b = button.lower().strip()
    with _GLOBAL_INPUT_LOCK:
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
    with _GLOBAL_INPUT_LOCK:
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
    with _GLOBAL_INPUT_LOCK:
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

def mouse_drag(start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int = 250, button: str = "left") -> bool:
    """
    Executes a continuous, distance-interpolated mouse drag with thread-safe global input serialization,
    active window focus monitoring, and guaranteed atomic button release.
    """
    if not IS_WINDOWS:
        return True
    with _GLOBAL_INPUT_LOCK:
        screen_w, screen_h = get_screen_size()
        
        # Calculate Euclidean distance for dynamic interpolation density
        dist = math.hypot(end_x - start_x, end_y - start_y)
        steps = max(18, min(100, int(dist / 6)))
        
        # 1. Position cursor at start position
        norm_sx = int((start_x * 65535) / (screen_w - 1)) if screen_w > 1 else 0
        norm_sy = int((start_y * 65535) / (screen_h - 1)) if screen_h > 1 else 0
        ctypes.windll.user32.SetCursorPos(start_x, start_y)
        send_mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=norm_sx, dy=norm_sy)
        time.sleep(0.04)
        
        # 2. Press down with explicit atomic start coordinates
        flag_down = MOUSEEVENTF_LEFTDOWN if button == "left" else (MOUSEEVENTF_RIGHTDOWN if button == "right" else MOUSEEVENTF_MIDDLEDOWN)
        send_mouse_event(flag_down | MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=norm_sx, dy=norm_sy)
        HELD_BUTTONS.add(button)
        time.sleep(0.04)
        
        aborted = False
        try:
            # 3. Smoothly move across the trajectory using synchronized SetCursorPos and SendInput events
            for i in range(1, steps + 1):
                # Sample active foreground window periodically to detect accidental Snap Assist triggers
                if i % 6 == 0:
                    active = get_active_window_details()
                    if active and "snap assist" in (active.get("title") or "").lower():
                        logger.warning(f"Focus unexpectedly shifted to Snap Assist during drag ({start_x},{start_y} -> {end_x},{end_y}). Aborting stroke.")
                        aborted = True
                        break
                
                t = i / steps
                curr_x = int(start_x + (end_x - start_x) * t)
                curr_y = int(start_y + (end_y - start_y) * t)
                norm_x = int((curr_x * 65535) / (screen_w - 1)) if screen_w > 1 else 0
                norm_y = int((curr_y * 65535) / (screen_h - 1)) if screen_h > 1 else 0
                ctypes.windll.user32.SetCursorPos(curr_x, curr_y)
                send_mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=norm_x, dy=norm_y)
                time.sleep(0.010)
            time.sleep(0.04)
        finally:
            # 4. Release button unconditionally at end coordinates
            norm_ex = int((end_x * 65535) / (screen_w - 1)) if screen_w > 1 else 0
            norm_ey = int((end_y * 65535) / (screen_h - 1)) if screen_h > 1 else 0
            flag_up = MOUSEEVENTF_LEFTUP if button == "left" else (MOUSEEVENTF_RIGHTUP if button == "right" else MOUSEEVENTF_MIDDLEUP)
            send_mouse_event(flag_up | MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=norm_ex, dy=norm_ey)
            HELD_BUTTONS.discard(button)
            time.sleep(0.04)
            
        return not aborted

def release_all_buttons():
    # Releases any mouse button currently registered in the HELD_BUTTONS set
    with _GLOBAL_INPUT_LOCK:
        for button in list(HELD_BUTTONS):
            mouse_up(button)
        HELD_BUTTONS.clear()

# --- Windows Management Injection ---

def _attach_thread_to_desktop():
    if not IS_WINDOWS:
        return
    try:
        # DESKTOP_ALL_ACCESS = 0x01FF
        hdesk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x01FF)
        if not hdesk:
            hdesk = ctypes.windll.user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            ctypes.windll.user32.SetThreadDesktop(hdesk)
    except Exception:
        pass

def get_active_window_details() -> Optional[Dict[str, Any]]:
    if not IS_WINDOWS:
        return {
            "title": "Mock OS - Desktop",
            "process": "explorer.exe",
            "pid": 9999,
            "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080}
        }
        
    _attach_thread_to_desktop()
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
    from ctypes import wintypes
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    ctypes.windll.user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    ctypes.windll.user32.EnumWindows.restype = wintypes.BOOL
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
        
    _attach_thread_to_desktop()
    windows_list = []
    
    def enum_callback(hwnd, lparam):
        try:
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.encode('ascii', 'ignore').decode('ascii').strip()
                    if not title or title.lower() in ("popuphost", "program manager", "default ime", "msctfime ui"):
                        return True
                    
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
        except Exception:
            pass
        return True

    cb = WNDENUMPROC(enum_callback)
    ctypes.windll.user32.EnumWindows(cb, 0)
    return windows_list

def focus_window(hwnd: int) -> bool:
    if not IS_WINDOWS:
        return True
        
    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return False
        
    fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
    if fg_hwnd == hwnd:
        return True

    current_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
    fg_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
    target_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)

    # Attach input queues to bypass Windows foreground lockout
    attached = False
    if fg_thread_id and fg_thread_id != current_thread_id:
        attached = bool(ctypes.windll.user32.AttachThreadInput(current_thread_id, fg_thread_id, True))
    if target_thread_id and target_thread_id != current_thread_id:
        ctypes.windll.user32.AttachThreadInput(current_thread_id, target_thread_id, True)

    try:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
        if ctypes.windll.user32.IsIconic(hwnd):
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
            
        time.sleep(0.03)
        ctypes.windll.user32.BringWindowToTop(hwnd)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.SetActiveWindow(hwnd)
        ctypes.windll.user32.SetFocus(hwnd)
    finally:
        if attached:
            ctypes.windll.user32.AttachThreadInput(current_thread_id, fg_thread_id, False)
        if target_thread_id and target_thread_id != current_thread_id:
            ctypes.windll.user32.AttachThreadInput(current_thread_id, target_thread_id, False)

    return True

def close_window(hwnd: int) -> bool:
    if not IS_WINDOWS:
        return True
        
    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return False
        
    success = ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    return bool(success)

def get_window_content_bounds(hwnd_or_win: Any) -> Dict[str, int]:
    """
    Calculates the safe, usable content/canvas area for a window,
    distinguishing window frame bounds from interior content/canvas regions.
    Excludes non-client title bar captions, window borders, and ribbon toolbars.
    """
    if isinstance(hwnd_or_win, dict):
        bounds = hwnd_or_win.get("bounds", {"x": 0, "y": 0, "width": 1920, "height": 1080})
        proc = (hwnd_or_win.get("process") or "").lower()
        title = (hwnd_or_win.get("title") or "").lower()
    else:
        hwnd = int(hwnd_or_win) if hwnd_or_win else 0
        details = None
        for w in list_desktop_windows():
            if w["hwnd"] == hwnd:
                details = w
                break
        if details:
            bounds = details["bounds"]
            proc = (details.get("process") or "").lower()
            title = (details.get("title") or "").lower()
        else:
            bounds = {"x": 0, "y": 0, "width": 1920, "height": 1080}
            proc = ""
            title = ""

    bx = bounds["x"]
    by = bounds["y"]
    bw = bounds["width"]
    bh = bounds["height"]

    is_paint = ("mspaint" in proc or "paint" in proc or "paint" in title)
    is_notepad = ("notepad" in proc or "notepad" in title)

    if is_paint:
        # In modern Windows 11 Paint with Per-Monitor DPI scaling:
        # Top title bar + ribbon toolbar (File, Edit, Brushes, Colors, Shapes) is ~430px
        # Safe usable white canvas starts at top_offset = 450px
        # Left side margin is ~100px, right margin ~100px, bottom status bar is ~80px
        top_offset = 450
        left_margin = 100
        right_margin = 100
        bottom_margin = 80
        is_canvas = True
    elif is_notepad:
        top_offset = 80
        left_margin = 20
        right_margin = 20
        bottom_margin = 30
        is_canvas = False
    else:
        # Generic window: title bar is ~50px, border is ~10px
        top_offset = 55
        left_margin = 15
        right_margin = 15
        bottom_margin = 20
        is_canvas = False

    content_w = max(50, bw - (left_margin + right_margin))
    content_h = max(50, bh - (top_offset + bottom_margin))

    return {
        "x": bx + left_margin,
        "y": by + top_offset,
        "width": content_w,
        "height": content_h,
        "window_x": bx,
        "window_y": by,
        "window_width": bw,
        "window_height": bh,
        "top_offset": top_offset,
        "left_margin": left_margin,
        "is_canvas": is_canvas
    }

def resolve_coordinates(arguments: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, int]], Optional[str]]:
    """
    Resolves input coordinates across:
    - SCREEN COORDINATES (absolute monitor pixels)
    - WINDOW COORDINATES (relative to window outer frame)
    - CONTENT/CANVAS COORDINATES (relative to usable content area)

    Prevents:
    - Dragging window title bars (which moves windows and triggers Snap Assist)
    - Reaching screen edges / snap zones unintentionally
    - Inputting coordinates outside the active monitor / window boundaries

    Returns: (success, resolved_coords_dict, error_message)
    """
    target_window = arguments.get("target_window")
    if not target_window and "target" in arguments:
        target_obj = arguments["target"]
        if isinstance(target_obj, dict):
            target_window = target_obj.get("window")

    coord_space = str(arguments.get("coordinate_space", "")).lower().strip()
    is_drag = "start_x" in arguments
    screen_w, screen_h = get_screen_size()

    if is_drag:
        start_x = int(arguments.get("start_x", 0))
        start_y = int(arguments.get("start_y", 0))
        end_x = int(arguments.get("end_x", 0))
        end_y = int(arguments.get("end_y", 0))
    else:
        x = int(arguments.get("x", 0))
        y = int(arguments.get("y", 0))

    # Retrieve scaling metadata if available
    scale_x = 1.0
    scale_y = 1.0
    latest_obs = None
    try:
        from agent.core.vision import SCREEN_OBSERVER
        latest_obs = SCREEN_OBSERVER.latest_observation
    except Exception:
        pass

    if latest_obs and "scale_factors" in latest_obs:
        scale_x = float(latest_obs["scale_factors"].get("scale_x", 1.0))
        scale_y = float(latest_obs["scale_factors"].get("scale_y", 1.0))

    if coord_space == "screenshot":
        if is_drag:
            start_x = int(start_x * scale_x)
            start_y = int(start_y * scale_y)
            end_x = int(end_x * scale_x)
            end_y = int(end_y * scale_y)
        else:
            x = int(x * scale_x)
            y = int(y * scale_y)

    if not target_window:
        # Raw screen coordinate path
        if is_drag:
            # Prevent drags that collide with screen top Snap Assist triggers (y <= 5)
            if start_y <= 5 or end_y <= 5:
                return False, None, "Drag coordinates touch screen top edge (y <= 5) which triggers Windows Snap Assist."
            if not (0 <= start_x < screen_w) or not (0 <= start_y < screen_h) or \
               not (0 <= end_x < screen_w) or not (0 <= end_y < screen_h):
                return False, None, f"Drag coordinates ({start_x},{start_y} -> {end_x},{end_y}) are outside screen boundaries ({screen_w}x{screen_h})."
            res = {"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y}
            logger.info(f"[COORDINATE RESOLUTION DIAGNOSTIC] Space={coord_space or 'screen'} Raw={arguments} Scale=({scale_x:.2f},{scale_y:.2f}) -> Resolved={res}")
            return True, res, None
        else:
            if not (0 <= x < screen_w) or not (0 <= y < screen_h):
                return False, None, f"Coordinates ({x}, {y}) are outside screen boundaries ({screen_w}x{screen_h})."
            res = {"x": x, "y": y}
            logger.info(f"[COORDINATE RESOLUTION DIAGNOSTIC] Space={coord_space or 'screen'} Raw={arguments} Scale=({scale_x:.2f},{scale_y:.2f}) -> Resolved={res}")
            return True, res, None

    # Lookup target window
    windows = list_desktop_windows()
    target_hwnd = None
    target_win = None

    for w in windows:
        if target_window.lower() in w.get("title", "").lower() or target_window.lower() in w.get("process", "").lower():
            target_hwnd = w.get("hwnd", 1)
            target_win = w
            break

    if not target_win:
        return False, None, f"Target window '{target_window}' not found on desktop."

    if target_hwnd:
        focus_window(target_hwnd)
    
    if IS_WINDOWS and target_hwnd and ctypes.windll.user32.IsWindow(target_hwnd):
        if ctypes.windll.user32.IsIconic(target_hwnd):
            return False, None, f"Target window '{target_window}' is minimized."
        if not ctypes.windll.user32.IsWindowVisible(target_hwnd):
            return False, None, f"Target window '{target_window}' is invisible."

    bounds = target_win["bounds"]
    if bounds["width"] <= 0 or bounds["height"] <= 0:
        return False, None, f"Target window '{target_window}' has invalid boundaries ({bounds['width']}x{bounds['height']})."

    content_bounds = get_window_content_bounds(target_win)

    # Determine coordinate space: if content/canvas space, or default for canvas apps (e.g. Paint)
    use_content_space = (coord_space in ("content", "canvas")) or (content_bounds["is_canvas"] and coord_space != "window")

    if use_content_space:
        base_x = content_bounds["x"]
        base_y = content_bounds["y"]
        max_w = content_bounds["width"]
        max_h = content_bounds["height"]
        space_name = "content/canvas"
    else:
        base_x = bounds["x"]
        base_y = bounds["y"]
        max_w = bounds["width"]
        max_h = bounds["height"]
        space_name = "window"

    if is_drag:
        # Check that relative coordinates are within target space
        if (start_x < 0 or start_x > max_w or start_y < 0 or start_y > max_h or
            end_x < 0 or end_x > max_w or end_y < 0 or end_y > max_h):
            # If coordinates are already absolute screen coords within bounds, keep them
            if (bounds["x"] <= start_x < bounds["x"] + bounds["width"] and
                bounds["y"] <= start_y < bounds["y"] + bounds["height"] and
                bounds["x"] <= end_x < bounds["x"] + bounds["width"] and
                bounds["y"] <= end_y < bounds["y"] + bounds["height"]):
                abs_start_x = start_x
                abs_start_y = start_y
                abs_end_x = end_x
                abs_end_y = end_y
            else:
                return False, None, f"Drag coordinates exceed {space_name} bounds (max: {max_w}x{max_h})."
        else:
            abs_start_x = base_x + start_x
            abs_start_y = base_y + start_y
            abs_end_x = base_x + end_x
            abs_end_y = base_y + end_y

        # Prevent dragging on title bar header
        if abs_start_y < bounds["y"] + 45 or abs_end_y < bounds["y"] + 45:
            return False, None, "Drag coordinates target the window title bar/caption area, which triggers window movements and Snap Assist instead of drawing."

        # Verify absolute screen bounds
        if not (0 <= abs_start_x < screen_w) or not (0 <= abs_start_y < screen_h) or \
           not (0 <= abs_end_x < screen_w) or not (0 <= abs_end_y < screen_h):
            return False, None, f"Converted drag coordinates ({abs_start_x},{abs_start_y} -> {abs_end_x},{abs_end_y}) are outside screen boundaries."

        res = {
            "start_x": abs_start_x,
            "start_y": abs_start_y,
            "end_x": abs_end_x,
            "end_y": abs_end_y
        }
        logger.info(f"[COORDINATE RESOLUTION DIAGNOSTIC] Space={coord_space or space_name} Target='{target_window}' Raw={arguments} Base=({base_x},{base_y}) Scale=({scale_x:.2f},{scale_y:.2f}) -> Resolved={res}")
        return True, res, None
    else:
        if x < 0 or x > max_w or y < 0 or y > max_h:
            if bounds["x"] <= x < bounds["x"] + bounds["width"] and bounds["y"] <= y < bounds["y"] + bounds["height"]:
                abs_x = x
                abs_y = y
            else:
                return False, None, f"Coordinates ({x}, {y}) exceed {space_name} bounds (max: {max_w}x{max_h})."
        else:
            abs_x = base_x + x
            abs_y = base_y + y

        if not (0 <= abs_x < screen_w) or not (0 <= abs_y < screen_h):
            return False, None, f"Converted coordinates ({abs_x}, {abs_y}) are outside screen boundaries."

        res = {"x": abs_x, "y": abs_y}
        logger.info(f"[COORDINATE RESOLUTION DIAGNOSTIC] Space={coord_space or space_name} Target='{target_window}' Raw={arguments} Base=({base_x},{base_y}) Scale=({scale_x:.2f},{scale_y:.2f}) -> Resolved={res}")
        return True, res, None

def get_installed_applications():
    """
    Retrieves the complete list of installed applications, system utilities,
    Start Menu programs, and AppX store apps on the system.
    """
    import sys
    import os
    if sys.platform != "win32":
        return [
            {"name": "Docker Desktop", "version": "4.71.0", "publisher": "Docker Inc.", "key": "docker"},
            {"name": "Blender", "version": "5.0.0", "publisher": "Blender Foundation", "key": "blender"},
            {"name": "Google Chrome", "version": "120.0.0", "publisher": "Google LLC", "key": "chrome"},
            {"name": "Microsoft Edge", "version": "151.0", "publisher": "Microsoft Corporation", "key": "edge"}
        ]
        
    try:
        import winreg
    except ImportError:
        return []

    apps = []
    seen_names = set()

    # 1. Start Menu Shortcuts (.lnk files) from All Users and Current User
    start_menu_paths = []
    prog_data = os.environ.get("ProgramData")
    if prog_data:
        start_menu_paths.append(os.path.join(prog_data, r"Microsoft\Windows\Start Menu\Programs"))
    app_data = os.environ.get("APPDATA")
    if app_data:
        start_menu_paths.append(os.path.join(app_data, r"Microsoft\Windows\Start Menu\Programs"))

    for sm_root in start_menu_paths:
        if not os.path.exists(sm_root):
            continue
        for root, dirs, files in os.walk(sm_root):
            for f in files:
                if f.lower().endswith(".lnk"):
                    app_name = f[:-4].strip()
                    norm = app_name.lower()
                    if norm in seen_names:
                        continue
                    if "uninstall" in norm or "help" in norm or "documentation" in norm or "read me" in norm:
                        continue
                    
                    seen_names.add(norm)
                    rel_folder = os.path.basename(root)
                    publisher = rel_folder if rel_folder.lower() not in ("programs", "start menu") else "Installed Application"
                    apps.append({
                        "name": app_name,
                        "version": "Shortcut",
                        "publisher": publisher,
                        "key": os.path.join(root, f)
                    })

    # 2. Windows Registry Uninstall Keys (HKLM 64-bit, HKLM 32-bit, HKCU)
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
    ]
    
    for hive, path in reg_paths:
        try:
            with winreg.OpenKey(hive, path) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            try:
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                if not display_name:
                                    continue
                                
                                display_name = display_name.strip()
                                norm = display_name.lower()
                                if norm in seen_names:
                                    continue
                                
                                if norm.startswith("kb") or "security update" in norm or "hotfix" in norm:
                                    continue
                                
                                version = ""
                                try:
                                    version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                                except Exception:
                                    pass
                                
                                publisher = ""
                                try:
                                    publisher = winreg.QueryValueEx(subkey, "Publisher")[0]
                                except Exception:
                                    pass
                                
                                seen_names.add(norm)
                                apps.append({
                                    "name": display_name,
                                    "version": str(version),
                                    "publisher": str(publisher),
                                    "key": subkey_name
                                })
                            except (OSError, IndexError):
                                pass
                    except OSError:
                        pass
        except OSError:
            pass

    # 3. Windows Store / Modern AppX Packages
    appx_reg = (winreg.HKEY_CURRENT_USER, r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages")
    try:
        with winreg.OpenKey(appx_reg[0], appx_reg[1]) as key:
            num = winreg.QueryInfoKey(key)[0]
            for i in range(num):
                try:
                    pkg_name = winreg.EnumKey(key, i)
                    parts = pkg_name.split("_")
                    if parts:
                        raw = parts[0]
                        if "." in raw:
                            prefix, app_part = raw.split(".", 1)
                            if len(prefix) <= 16 or any(c.isdigit() for c in prefix):
                                clean_name = app_part
                            else:
                                clean_name = raw
                        else:
                            clean_name = raw
                            
                        clean_name = clean_name.replace("Microsoft.", "").replace("Windows.", "").replace("Desktop", " Desktop")
                        norm = clean_name.lower()
                        if (
                            not clean_name or 
                            len(clean_name) < 3 or 
                            clean_name[0].isdigit() or
                            norm in seen_names or 
                            norm.startswith("microsoftwindows") or
                            norm.startswith("microsoft.ui") or
                            norm.startswith("microsoft.vclibs") or
                            norm.startswith("microsoft.net") or
                            any(token in norm for token in ["cbs", "xaml", "brokerplugin", "services.store", "appinstaller", "syncengine", "filons", "taskbar", "voiess", "speion", "inpapp", "livtop", "tasbar"]) or
                            (len(clean_name) > 25 and "-" in clean_name and any(c.isdigit() for c in clean_name))
                        ):
                            continue
                            
                        seen_names.add(norm)
                        apps.append({
                            "name": clean_name,
                            "version": parts[1] if len(parts) > 1 else "AppX",
                            "publisher": "Microsoft Corporation" if "microsoft" in pkg_name.lower() else "Windows Store",
                            "key": pkg_name
                        })
                except Exception:
                    pass
    except Exception:
        pass

    # 4. Standard Core Windows Tools
    core_tools = [
        ("Calculator", "System Tool", "Microsoft Corporation", "calc.exe"),
        ("Notepad", "System Tool", "Microsoft Corporation", "notepad.exe"),
        ("Paint", "System Tool", "Microsoft Corporation", "mspaint.exe"),
        ("File Explorer", "System Tool", "Microsoft Corporation", "explorer.exe"),
        ("Command Prompt", "System Tool", "Microsoft Corporation", "cmd.exe"),
        ("Windows PowerShell", "System Tool", "Microsoft Corporation", "powershell.exe"),
        ("Task Manager", "System Tool", "Microsoft Corporation", "taskmgr.exe"),
        ("Snipping Tool", "System Tool", "Microsoft Corporation", "snippingtool.exe"),
        ("Registry Editor", "System Tool", "Microsoft Corporation", "regedit.exe"),
        ("Control Panel", "System Tool", "Microsoft Corporation", "control.exe"),
        ("Windows Settings", "System Tool", "Microsoft Corporation", "ms-settings:"),
        ("Device Manager", "System Tool", "Microsoft Corporation", "devmgmt.msc"),
        ("Disk Management", "System Tool", "Microsoft Corporation", "diskmgmt.msc"),
        ("Services", "System Tool", "Microsoft Corporation", "services.msc"),
        ("Resource Monitor", "System Tool", "Microsoft Corporation", "resmon.exe"),
        ("Character Map", "System Tool", "Microsoft Corporation", "charmap.exe")
    ]
    for name, ver, pub, key in core_tools:
        if name.lower() not in seen_names:
            seen_names.add(name.lower())
            apps.append({
                "name": name,
                "version": ver,
                "publisher": pub,
                "key": key
            })

    # Sort alphabetically
    apps.sort(key=lambda x: x["name"].lower())
    return apps

