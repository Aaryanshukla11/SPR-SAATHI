import os
import io
import time
import uuid
import base64
import ctypes
from ctypes import wintypes
import datetime
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image

from agent.core import win32_utils

# Base directory for temporary screenshots
SCREENSHOTS_BASE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "screenshots"
)

class ScreenshotLifecycleManager:
    """
    Manages the lifecycle, storage, and cleanup of temporary visual observation screenshots.
    Ensures screenshots do not accumulate unbounded on disk.
    """
    def __init__(self, base_dir: str = SCREENSHOTS_BASE_DIR, max_recent_per_task: int = 5):
        self.base_dir = base_dir
        self.max_recent_per_task = max_recent_per_task
        os.makedirs(self.base_dir, exist_ok=True)

    def get_task_dir(self, task_id: Optional[str]) -> str:
        tid = task_id or "global"
        # Sanitize task_id for directory naming
        clean_tid = "".join(c for c in tid if c.isalnum() or c in ("-", "_")).strip() or "global"
        task_dir = os.path.join(self.base_dir, clean_tid)
        os.makedirs(task_dir, exist_ok=True)
        return task_dir

    def prune_old_screenshots_for_task(self, task_id: Optional[str]):
        """Retains only the most recent N screenshots for a given active task."""
        try:
            task_dir = self.get_task_dir(task_id)
            if not os.path.exists(task_dir):
                return
            files = [
                os.path.join(task_dir, f)
                for f in os.listdir(task_dir)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            ]
            if len(files) > self.max_recent_per_task:
                # Sort by modification time ascending (oldest first)
                files.sort(key=lambda x: os.path.getmtime(x))
                to_delete = files[:-self.max_recent_per_task]
                for fpath in to_delete:
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
        except Exception:
            pass

    def cleanup_task_screenshots(self, task_id: Optional[str]):
        """Deletes all screenshots associated with a completed or cancelled task."""
        try:
            task_dir = self.get_task_dir(task_id)
            if os.path.exists(task_dir):
                for f in os.listdir(task_dir):
                    fpath = os.path.join(task_dir, f)
                    try:
                        if os.path.isfile(fpath):
                            os.remove(fpath)
                    except Exception:
                        pass
                try:
                    os.rmdir(task_dir)
                except Exception:
                    pass
        except Exception:
            pass

    def cleanup_stale_directories(self, max_age_seconds: float = 3600.0):
        """Cleans up any orphaned task screenshot directories older than max_age_seconds."""
        try:
            if not os.path.exists(self.base_dir):
                return
            now = time.time()
            for d in os.listdir(self.base_dir):
                dir_path = os.path.join(self.base_dir, d)
                if os.path.isdir(dir_path):
                    mtime = os.path.getmtime(dir_path)
                    if now - mtime > max_age_seconds:
                        self.cleanup_task_screenshots(d)
        except Exception:
            pass


class ScreenObserver:
    """
    High-reliability screen observation engine for SPR SAATHI.
    Captures full desktop and active window visuals via Win32 GDI BitBlt with PIL fallback,
    generates optimized multimodal base64 image representations, and structures visual metadata.
    """
    def __init__(self, lifecycle_manager: Optional[ScreenshotLifecycleManager] = None):
        self.lifecycle_manager = lifecycle_manager or ScreenshotLifecycleManager()
        self.latest_observation: Optional[Dict[str, Any]] = None
        self._init_win32_dpi()

    def _init_win32_dpi(self):
        """Ensure the process is DPI-aware so screenshots match real physical coordinates."""
        if win32_utils.IS_WINDOWS:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass

    def _capture_screen_gdi(self) -> Optional[Image.Image]:
        """Captures the full virtual desktop using Win32 GDI BitBlt."""
        if not win32_utils.IS_WINDOWS:
            return None

        try:
            win32_utils._attach_thread_to_desktop()
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            # Virtual screen coordinates spanning all monitors
            left = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
            top = user32.GetSystemMetrics(77)    # SM_YVIRTUALSCREEN
            width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            height = user32.GetSystemMetrics(79) # SM_CYVIRTUALSCREEN

            if width <= 0 or height <= 0:
                width = user32.GetSystemMetrics(0) # SM_CXSCREEN
                height = user32.GetSystemMetrics(1) # SM_CYSCREEN
                left = 0
                top = 0

            if width <= 0 or height <= 0:
                return None

            hdc_screen = user32.GetDC(0)
            if not hdc_screen:
                return None

            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            if not hdc_mem:
                user32.ReleaseDC(0, hdc_screen)
                return None

            hbm = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
            if not hbm:
                gdi32.DeleteDC(hdc_mem)
                user32.ReleaseDC(0, hdc_screen)
                return None

            hbm_old = gdi32.SelectObject(hdc_mem, hbm)

            # SRCCOPY (0x00CC0020) | CAPTUREBLT (0x40000000)
            gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, left, top, 0x00CC0020 | 0x40000000)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = width
            bmi.biHeight = -height # Top-down DIB
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0 # BI_RGB

            buffer_size = width * height * 4
            buf = ctypes.create_string_buffer(buffer_size)

            lines = gdi32.GetDIBits(hdc_mem, hbm, 0, height, buf, ctypes.byref(bmi), 0)

            # Cleanup GDI handles
            gdi32.SelectObject(hdc_mem, hbm_old)
            gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)

            if lines == height:
                img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
                return img.convert("RGB")
            return None
        except Exception:
            return None

    def _capture_screen_fallback(self) -> Optional[Image.Image]:
        """Fallback capture via PIL ImageGrab."""
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True)
            if img:
                return img.convert("RGB")
        except Exception:
            pass
        return None

    def capture_image(self) -> Optional[Image.Image]:
        """Attempts primary GDI capture, falling back to PIL ImageGrab."""
        img = self._capture_screen_gdi()
        if img is None:
            img = self._capture_screen_fallback()
        return img

    def capture_observation(
        self,
        task_id: Optional[str] = None,
        max_dimension: int = 1280,
        quality: int = 70
    ) -> Dict[str, Any]:
        """
        Captures the current visual and structural desktop observation.
        
        Returns:
            Dict containing:
                - timestamp (ISO-8601 UTC)
                - active_window (dict with hwnd, title, process, bounds, is_minimized)
                - visible_windows (list of desktop windows)
                - screen (width, height)
                - cursor (x, y)
                - image_path (local path to saved temporary screenshot)
                - image_base64 (compressed JPEG base64 string for multimodal vision reasoning)
                - image_available (bool)
                - observation_error (optional error message if capture failed)
        """
        now_str = datetime.datetime.utcnow().isoformat() + "Z"

        # 1. Structural Window & Cursor State
        active_window = win32_utils.get_active_window_details()
        visible_windows = win32_utils.list_desktop_windows()
        screen_w, screen_h = win32_utils.get_screen_size()
        cursor_x, cursor_y = win32_utils.get_cursor_position()

        obs: Dict[str, Any] = {
            "timestamp": now_str,
            "active_window": active_window,
            "visible_windows": visible_windows,
            "screen": {"width": screen_w, "height": screen_h},
            "cursor": {"x": cursor_x, "y": cursor_y},
            "image_path": None,
            "image_base64": None,
            "image_available": False,
            "observation_error": None
        }

        # 2. Visual Screenshot Capture
        try:
            img = self.capture_image()
            if img is not None:
                orig_w, orig_h = img.size
                obs["screen"]["width"] = orig_w
                obs["screen"]["height"] = orig_h

                # Scale down for efficient multimodal reasoning while preserving UI text legibility
                if max(orig_w, orig_h) > max_dimension:
                    scale = max_dimension / float(max(orig_w, orig_h))
                    new_w = int(orig_w * scale)
                    new_h = int(orig_h * scale)
                    scaled_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                else:
                    scaled_img = img

                # Encode to JPEG Base64
                buffer = io.BytesIO()
                scaled_img.save(buffer, format="JPEG", quality=quality, optimize=True)
                img_bytes = buffer.getvalue()
                img_b64 = base64.b64encode(img_bytes).decode("utf-8")

                # Save temporary file in task screenshot directory
                task_dir = self.lifecycle_manager.get_task_dir(task_id)
                shot_filename = f"shot_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}.jpg"
                shot_path = os.path.join(task_dir, shot_filename)
                scaled_img.save(shot_path, format="JPEG", quality=quality)

                # Prune older screenshots to bound disk space
                self.lifecycle_manager.prune_old_screenshots_for_task(task_id)

                obs["image_path"] = shot_path
                obs["image_base64"] = img_b64
                obs["image_available"] = True
                obs["physical_dimensions"] = {"width": orig_w, "height": orig_h}
                obs["screenshot_dimensions"] = {"width": new_w, "height": new_h}
                obs["scale_factors"] = {
                    "scale_x": orig_w / float(new_w) if new_w > 0 else 1.0,
                    "scale_y": orig_h / float(new_h) if new_h > 0 else 1.0
                }
            else:
                obs["observation_error"] = "Screen capture returned null image from GDI and PIL subsystems."
        except Exception as e:
            obs["observation_error"] = f"Visual capture exception: {str(e)}"

        self.latest_observation = obs
        return obs

def verify_visual_change(
    img_before: Optional[Any],
    img_after: Optional[Any],
    region_bbox: Optional[Tuple[int, int, int, int]] = None,
    pixel_diff_threshold: int = 25,
    min_changed_pixels: int = 15
) -> Dict[str, Any]:
    """
    Compares two screenshots or cropped regions before and after an action
    to mathematically verify whether a visible change occurred on screen.

    Returns:
        Dict containing:
            - verification_status: "verified_success" | "execution_success_but_unverified" | "verification_failed"
            - change_detected: bool
            - pixels_changed: int
            - change_percentage: float
            - diff_bounding_box: Optional[Tuple[int, int, int, int]]
            - error: Optional[str]
    """
    from PIL import ImageChops
    
    if img_before is None or img_after is None:
        return {
            "verification_status": "execution_success_but_unverified",
            "change_detected": False,
            "pixels_changed": 0,
            "change_percentage": 0.0,
            "diff_bounding_box": None,
            "error": "One or both screenshot images were unavailable for visual comparison."
        }

    try:
        # Load images if file paths or base64
        if isinstance(img_before, str):
            if os.path.exists(img_before):
                im_b = Image.open(img_before)
            else:
                im_b = Image.open(io.BytesIO(base64.b64decode(img_before)))
        else:
            im_b = img_before

        if isinstance(img_after, str):
            if os.path.exists(img_after):
                im_a = Image.open(img_after)
            else:
                im_a = Image.open(io.BytesIO(base64.b64decode(img_after)))
        else:
            im_a = img_after

        # Ensure identical sizes
        if im_b.size != im_a.size:
            im_a = im_a.resize(im_b.size)

        # Crop if region specified
        if region_bbox:
            w, h = im_b.size
            x1 = max(0, min(w - 1, region_bbox[0]))
            y1 = max(0, min(h - 1, region_bbox[1]))
            x2 = max(x1 + 1, min(w, region_bbox[2]))
            y2 = max(y1 + 1, min(h, region_bbox[3]))
            im_b = im_b.crop((x1, y1, x2, y2))
            im_a = im_a.crop((x1, y1, x2, y2))

        # Convert to RGB
        im_b_rgb = im_b.convert("RGB")
        im_a_rgb = im_a.convert("RGB")

        diff = ImageChops.difference(im_b_rgb, im_a_rgb)
        diff_bbox = diff.getbbox()

        diff_gray = diff.convert("L")
        try:
            pixels = list(diff_gray.get_flattened_data())
        except AttributeError:
            pixels = list(diff_gray.getdata())

        total_pixels = len(pixels)
        changed_pixels = sum(1 for p in pixels if p >= pixel_diff_threshold)
        pct = (changed_pixels / total_pixels * 100.0) if total_pixels > 0 else 0.0

        if changed_pixels >= min_changed_pixels:
            return {
                "verification_status": "verified_success",
                "change_detected": True,
                "pixels_changed": changed_pixels,
                "change_percentage": round(pct, 4),
                "diff_bounding_box": diff_bbox,
                "error": None
            }
        else:
            return {
                "verification_status": "verification_failed",
                "change_detected": False,
                "pixels_changed": changed_pixels,
                "change_percentage": round(pct, 4),
                "diff_bounding_box": None,
                "error": "No visual difference detected in the target canvas/screen region after action execution."
            }
    except Exception as e:
        return {
            "verification_status": "execution_success_but_unverified",
            "change_detected": False,
            "pixels_changed": 0,
            "change_percentage": 0.0,
            "diff_bounding_box": None,
            "error": f"Visual verification calculation error: {str(e)}"
        }

# Global singleton instance for use across SPR SAATHI runtime
SCREEN_OBSERVER = ScreenObserver()
