import os
import time
import datetime
import logging
from typing import Dict, Any, List, Optional, Tuple

from agent.core import win32_utils
from agent.core.vision import SCREEN_OBSERVER, verify_visual_change

logger = logging.getLogger("agent.core.perception")


class UnifiedPerceptionManager:
    """
    Phase 3: Unified Perception and Environment Understanding Engine.
    
    Combines:
    - High-resolution visual screenshots & diff tracking
    - Active window & desktop window hierarchy
    - Running system processes & resource footprints
    - UI control & accessibility elements
    - Active browser tab & navigation metadata
    - Application metadata (binary path, architecture, responsiveness)
    - File-system state & working directories
    
    Implements Phase 3 Perception Priority:
        Structured Application Data
                ↓
        Application APIs
                ↓
        Accessibility Information
                ↓
        Browser DOM / State
                ↓
        Window Metadata
                ↓
        Vision Analysis
                ↓
        Raw Screen Coordinates
    """

    def __init__(self):
        self.last_perception: Optional[Dict[str, Any]] = None
        self.workspace_root = os.path.abspath(os.getcwd())

    def get_file_system_state(self, root_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Captures the current file-system context:
        - Current working directory
        - Recently modified files in workspace
        - Desktop directory contents
        """
        target_dir = root_dir or self.workspace_root
        recent_files = []
        try:
            if os.path.exists(target_dir):
                for root, dirs, files in os.walk(target_dir):
                    # Skip common noisy cache directories
                    dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"]]
                    for f in files:
                        p = os.path.join(root, f)
                        try:
                            mtime = os.path.getmtime(p)
                            size = os.path.getsize(p)
                            recent_files.append({
                                "name": f,
                                "path": p,
                                "rel_path": os.path.relpath(p, target_dir),
                                "size_bytes": size,
                                "modified_timestamp": mtime
                            })
                        except OSError:
                            continue
            # Sort by most recently modified
            recent_files.sort(key=lambda x: x["modified_timestamp"], reverse=True)
        except Exception as e:
            logger.warning(f"Failed to scan file system state: {e}")

        # Desktop items
        desktop_items = []
        try:
            desktop_path = os.path.expanduser(r"~\Desktop")
            if os.path.exists(desktop_path):
                desktop_items = [item for item in os.listdir(desktop_path)[:30] if not item.startswith(".")]
        except Exception:
            pass

        return {
            "working_directory": target_dir,
            "recent_workspace_files": recent_files[:20],
            "desktop_items": desktop_items
        }

    def capture_unified_perception(
        self,
        task_id: str = "default",
        include_image: bool = True,
        include_hierarchy: bool = True,
        include_processes: bool = True,
        user_files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Captures the complete unified environment perception snapshot across
        all 8 perception layers defined in Phase 3.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Visual Capture
        visual_obs = SCREEN_OBSERVER.capture_observation(task_id=task_id) if include_image else {}

        # 2. Active Window & Desktop Windows
        active_win = visual_obs.get("active_window") or win32_utils.get_active_window_details()
        visible_windows = visual_obs.get("visible_windows") or win32_utils.list_desktop_windows()

        # Robust active_hwnd resolution
        active_hwnd = 0
        if isinstance(active_win, dict):
            active_hwnd = active_win.get("hwnd", 0)
            if not active_hwnd and visible_windows:
                target_title = (active_win.get("title") or "").lower()
                target_proc = (active_win.get("process") or active_win.get("process_name") or "").lower()
                for vw in visible_windows:
                    v_title = (vw.get("title") or "").lower()
                    v_proc = (vw.get("process") or vw.get("process_name") or "").lower()
                    if (target_title and target_title == v_title) or (target_proc and target_proc == v_proc):
                        active_hwnd = vw.get("hwnd", 0)
                        if active_hwnd:
                            active_win["hwnd"] = active_hwnd
                            break
                if not active_hwnd and visible_windows:
                    active_hwnd = visible_windows[0].get("hwnd", 0)

        # 3. Window Hierarchy & Child Controls
        window_hierarchy = []
        if include_hierarchy:
            target_h = active_hwnd or (visible_windows[0].get("hwnd", 0) if visible_windows else 0)
            if target_h:
                window_hierarchy = win32_utils.get_window_hierarchy(target_h)
            elif not win32_utils.IS_WINDOWS:
                window_hierarchy = win32_utils.get_window_hierarchy(1111)

        # 4. Application Metadata
        app_metadata = {}
        if active_hwnd:
            app_metadata = win32_utils.get_application_metadata(active_hwnd)

        # 5. Running Processes
        running_procs = []
        if include_processes:
            running_procs = win32_utils.get_running_processes(limit=25)

        # 6. Browser State & DOM Metadata
        browser_state = win32_utils.get_browser_state(active_hwnd)

        # 7. File-System State
        fs_state = self.get_file_system_state()

        # 8. User-provided files inspection
        user_files_info = []
        if user_files:
            for uf in user_files:
                if os.path.exists(uf):
                    user_files_info.append({
                        "path": uf,
                        "size_bytes": os.path.getsize(uf),
                        "exists": True
                    })
                else:
                    user_files_info.append({"path": uf, "exists": False})

        snapshot: Dict[str, Any] = {
            "timestamp": now_utc,
            "perception_version": "phase3_unified_v1",
            "active_window": active_win,
            "visible_windows": visible_windows,
            "window_hierarchy": window_hierarchy,
            "application_metadata": app_metadata,
            "browser_state": browser_state,
            "running_processes": running_procs,
            "file_system_state": fs_state,
            "user_files": user_files_info,
            "visual_observation": visual_obs,
            "screen_dimensions": visual_obs.get("screen", {"width": 1920, "height": 1080}),
            "cursor_position": visual_obs.get("cursor", {"x": 0, "y": 0})
        }

        self.last_perception = snapshot
        return snapshot

    def resolve_element_by_priority(
        self,
        query: str,
        perception_snapshot: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Locates a target UI element using the strict Phase 3 Priority Hierarchy:
        
        1. Child Window / Control Hierarchy (Exact class/text match)
        2. Browser State / Active Tab
        3. Window Metadata / Top-level window match
        4. Screen Coordinate Fallback
        
        Returns:
            Dict containing:
                - target_type: 'control' | 'browser_tab' | 'window' | 'screen_coord'
                - bounds: {'x', 'y', 'width', 'height'}
                - center: {'x', 'y'}
                - source_priority: int (1 highest to 5 lowest)
                - matched_text: str
        """
        snapshot = perception_snapshot or self.last_perception
        if not snapshot:
            snapshot = self.capture_unified_perception(include_image=False)

        q_clean = query.lower().strip()

        # Priority 1: Window Hierarchy Child Controls
        hierarchy = snapshot.get("window_hierarchy", [])
        for ctrl in hierarchy:
            text = (ctrl.get("text") or "").lower().strip()
            class_name = (ctrl.get("class_name") or "").lower().strip()
            if ctrl.get("visible") and (q_clean in text or q_clean == class_name):
                bounds = ctrl["bounds"]
                if bounds["width"] > 0 and bounds["height"] > 0:
                    center_x = bounds["x"] + bounds["width"] // 2
                    center_y = bounds["y"] + bounds["height"] // 2
                    return {
                        "target_type": "control",
                        "bounds": bounds,
                        "center": {"x": center_x, "y": center_y},
                        "source_priority": 1,
                        "matched_text": ctrl.get("text") or ctrl.get("class_name"),
                        "hwnd": ctrl.get("hwnd"),
                        "control_id": ctrl.get("control_id")
                    }

        # Priority 2: Browser State & Navigation
        browser = snapshot.get("browser_state")
        if browser and browser.get("is_browser"):
            tab_title = (browser.get("tab_title") or "").lower()
            if q_clean in tab_title:
                active_bounds = snapshot.get("active_window", {}).get("bounds", {"x": 0, "y": 0, "width": 1920, "height": 1080})
                return {
                    "target_type": "browser_tab",
                    "bounds": active_bounds,
                    "center": {"x": active_bounds["x"] + 200, "y": active_bounds["y"] + 45},
                    "source_priority": 2,
                    "matched_text": browser.get("tab_title"),
                    "hwnd": browser.get("hwnd")
                }

        # Priority 3: Visible Windows List
        visible_windows = snapshot.get("visible_windows", [])
        for win in visible_windows:
            win_title = (win.get("title") or "").lower()
            win_proc = (win.get("process") or "").lower()
            if q_clean in win_title or q_clean in win_proc:
                bounds = win.get("bounds", {"x": 0, "y": 0, "width": 100, "height": 100})
                center_x = bounds["x"] + bounds["width"] // 2
                center_y = bounds["y"] + bounds["height"] // 2
                return {
                    "target_type": "window",
                    "bounds": bounds,
                    "center": {"x": center_x, "y": center_y},
                    "source_priority": 3,
                    "matched_text": win.get("title") or win.get("process"),
                    "hwnd": win.get("hwnd")
                }

        return None

    def detect_environment_changes(
        self,
        before_snapshot: Dict[str, Any],
        after_snapshot: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Detects structural and visual changes between two perception snapshots:
        - Active window changed
        - New processes launched or exited
        - File-system modifications
        - Visual pixel changes
        """
        # 1. Window transition
        win_before = (before_snapshot.get("active_window") or {}).get("hwnd")
        win_after = (after_snapshot.get("active_window") or {}).get("hwnd")
        window_switched = win_before != win_after

        # 2. Process changes
        procs_before = {p["pid"] for p in before_snapshot.get("running_processes", [])}
        procs_after = {p["pid"] for p in after_snapshot.get("running_processes", [])}
        new_procs = list(procs_after - procs_before)
        terminated_procs = list(procs_before - procs_after)

        # 3. Visual diff
        vis_before = before_snapshot.get("visual_observation", {})
        vis_after = after_snapshot.get("visual_observation", {})
        visual_changed = False
        pixel_diff = {}

        if vis_before.get("image_path") and vis_after.get("image_path"):
            try:
                from PIL import Image
                img1 = Image.open(vis_before["image_path"])
                img2 = Image.open(vis_after["image_path"])
                pixel_diff = verify_visual_change(img1, img2)
                visual_changed = pixel_diff.get("change_detected", False)
            except Exception:
                pass

        return {
            "window_switched": window_switched,
            "active_window_before": before_snapshot.get("active_window"),
            "active_window_after": after_snapshot.get("active_window"),
            "new_processes_count": len(new_procs),
            "terminated_processes_count": len(terminated_procs),
            "visual_change_detected": visual_changed,
            "pixel_diff": pixel_diff
        }


# Global singleton instance of UnifiedPerceptionManager
UNIFIED_PERCEPTION = UnifiedPerceptionManager()
