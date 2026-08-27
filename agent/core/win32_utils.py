import ctypes
import time
import sys
from typing import Dict, Any, List, Optional

IS_WINDOWS = sys.platform == "win32"

# Constants for Input type
INPUT_KEYBOARD = 1

# Constants for Keyboard flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE = 0x0004

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
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

# Callback type for EnumWindows
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
