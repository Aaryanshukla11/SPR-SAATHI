import ctypes
from ctypes import wintypes
import logging

logger = logging.getLogger(__name__)

# Load Windows API DLLs
try:
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    # Declare DPI Awareness to ensure accurate screen geometry metrics
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
except Exception as e:
    logger.error(f"Failed to load Win32 DLLs: {e}")
    shell32 = None
    user32 = None

# Structs for AppBar positioning
class RECT(ctypes.Structure):
    _fields_ = [
        ('left', ctypes.c_long),
        ('top', ctypes.c_long),
        ('right', ctypes.c_long),
        ('bottom', ctypes.c_long)
    ]

class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_ulong),
        ('hWnd', ctypes.c_void_p),
        ('uCallbackMessage', ctypes.c_uint),
        ('uEdge', ctypes.c_uint),
        ('rc', RECT),
        ('lParam', ctypes.c_long)
    ]

# ABM Messages
ABM_NEW = 0
ABM_REMOVE = 1
ABM_QUERYPOS = 2
ABM_SETPOS = 3

# ABE Edges
ABE_LEFT = 0
ABE_TOP = 1
ABE_RIGHT = 2
ABE_BOTTOM = 3

_active_appbar_hwnd = None

def register_appbar(title="SPR SAATHI", side='right', width_ratio=0.25):
    """
    Finds the window by title and registers it as a Win32 AppBar.
    This reserves screen space so maximized applications only fill the remaining area.
    """
    global _active_appbar_hwnd
    if not user32 or not shell32:
        return False

    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False

    # Get work area width and height
    screen_width = user32.GetSystemMetrics(0)
    screen_height = user32.GetSystemMetrics(1)

    # Compute AppBar reservation width
    bar_width = int(screen_width * width_ratio)

    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    abd.uCallbackMessage = 0
    abd.uEdge = ABE_RIGHT if side == 'right' else ABE_LEFT

    # Setup the bounding RECT request
    if side == 'right':
        abd.rc.left = screen_width - bar_width
        abd.rc.top = 0
        abd.rc.right = screen_width
        abd.rc.bottom = screen_height
    else:
        abd.rc.left = 0
        abd.rc.top = 0
        abd.rc.right = bar_width
        abd.rc.bottom = screen_height

    # 1. Register AppBar
    shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
    _active_appbar_hwnd = hwnd

    # 2. Query and Set Position
    shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))

    # Recalculate based on query adjustment
    if side == 'right':
        abd.rc.left = screen_width - bar_width
    else:
        abd.rc.right = bar_width

    shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))

    # 3. Position the window exactly to match the reserved rect
    # SWP_NOACTIVATE | SWP_NOZORDER = 0x0010 | 0x0004 = 0x0014
    user32.SetWindowPos(
        hwnd,
        0,
        abd.rc.left,
        abd.rc.top,
        abd.rc.right - abd.rc.left,
        abd.rc.bottom - abd.rc.top,
        0x0014
    )
    
    logger.info(f"AppBar successfully docked. Reserved {bar_width}px on the {side} side.")
    return True

def unregister_appbar():
    """
    Unregisters the active AppBar, restoring system work area.
    """
    global _active_appbar_hwnd
    if not _active_appbar_hwnd or not shell32:
        return
    
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = _active_appbar_hwnd
    shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
    logger.info("AppBar unregistered. Desktop work area restored.")
    _active_appbar_hwnd = None
