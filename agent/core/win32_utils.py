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

def _attach_thread_to_desktop():
    if not IS_WINDOWS:
        return
    try:
        # DESKTOP_ALL_ACCESS = 0x01FF
        hdesk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x01FF)
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

def get_installed_applications():
    """
    Retrieves the complete list of installed applications, system utilities,
    Start Menu programs, and AppX store apps on the system.
    """
    import sys
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

