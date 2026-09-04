import subprocess
import os
import asyncio
from typing import Dict, Any
from .base import BaseTool
from agent.core import win32_utils

class LaunchAppTool(BaseTool):
    @property
    def name(self) -> str:
        return "launch_app"

    @property
    def description(self) -> str:
        return "Launch a Windows application by command name or path (e.g. notepad.exe, mspaint.exe)."

    @property
    def category(self) -> str:
        return "windows"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Executable name or file path to run (e.g. notepad.exe)"}
            },
            "required": ["app_name"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        app_name = arguments.get("app_name", "").strip()
        if not app_name:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": "Application name cannot be empty."
            }
            
        try:
            expanded_name = os.path.expandvars(app_name)
            clean_name = expanded_name.lower().strip()
            
            # Map packaged Windows 11 AppX modern apps to shell AppsFolder identifiers for reliable GUI window creation
            KNOWN_APPS_MAP = {
                "notepad": "shell:AppsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
                "notepad.exe": "shell:AppsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
                "mspaint": "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App",
                "mspaint.exe": "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App",
                "paint": "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App",
                "calc": "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
                "calc.exe": "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
                "calculator": "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
            }
            
            if clean_name in KNOWN_APPS_MAP:
                subprocess.Popen(["explorer.exe", KNOWN_APPS_MAP[clean_name]])
            elif hasattr(os, "startfile"):
                try:
                    os.startfile(expanded_name)
                except Exception:
                    subprocess.Popen(f'cmd.exe /c start "" "{expanded_name}"', shell=True)
            else:
                subprocess.Popen(f'cmd.exe /c start "" "{expanded_name}"', shell=True)
            ready_info = await win32_utils.wait_for_application_ready_async(clean_name, timeout=5.0)
            if ready_info.get("ready"):
                msg = f"Application '{app_name}' launched and confirmed ready (Window: '{ready_info.get('title')}', Process: '{ready_info.get('process')}')."
            else:
                msg = f"Application '{app_name}' launch command dispatched (Readiness detection ongoing)."
            return {
                "call_id": "",
                "success": True,
                "readiness": ready_info,
                "output": msg,
                "error": None
            }
        except FileNotFoundError:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": f"Application '{app_name}' not found. Please specify a valid executable name or absolute path."
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": f"Failed to launch application '{app_name}': {str(e)}"
            }


class ListWindowsTool(BaseTool):
    @property
    def name(self) -> str:
        return "list_windows"

    @property
    def description(self) -> str:
        return "List all visible, active application windows on the desktop."

    @property
    def category(self) -> str:
        return "windows"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {}
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            windows = win32_utils.list_desktop_windows()
            import json
            return {
                "call_id": "",
                "success": True,
                "windows": windows,
                "count": len(windows),
                "output": json.dumps(windows),
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": f"Failed to retrieve desktop windows list: {str(e)}"
            }


class FocusWindowTool(BaseTool):
    @property
    def name(self) -> str:
        return "focus_window"

    @property
    def description(self) -> str:
        return "Focus and bring a specific window to the foreground by its title or process name."

    @property
    def category(self) -> str:
        return "windows"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title_substring": {"type": "string", "description": "Substring to search for in window title (case-insensitive)"},
                "process_name": {"type": "string", "description": "Process name to search for (e.g. notepad.exe)"}
            }
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        title_sub = arguments.get("title_substring", "").strip().lower()
        proc_name = arguments.get("process_name", "").strip().lower()
        
        if not title_sub and not proc_name:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": "You must specify at least one search criterion: title_substring or process_name."
            }
            
        try:
            windows = win32_utils.list_desktop_windows()
            target_hwnd = None
            matched_title = ""
            
            for w in windows:
                # Match title or process
                title_match = bool(title_sub and (title_sub in w["title"].lower() or title_sub in w["process"].lower()))
                proc_match = bool(proc_name and (proc_name in w["process"].lower() or proc_name in w["title"].lower()))
                
                if (title_sub and proc_name and (title_match or proc_match)) or \
                   (title_sub and not proc_name and title_match) or \
                   (proc_name and not title_sub and proc_match):
                    target_hwnd = w["hwnd"]
                    matched_title = w["title"] or w["process"]
                    break
                    
            if not target_hwnd:
                criteria = []
                if title_sub: criteria.append(f"title='{title_sub}'")
                if proc_name: criteria.append(f"process='{proc_name}'")
                return {
                    "call_id": "",
                    "success": False,
                    "output": "",
                    "error": f"Window not found matching: {', '.join(criteria)}"
                }
                
            focused = win32_utils.focus_window(target_hwnd)
            fg_verified = win32_utils.verify_foreground_state(target_hwnd)
            if focused or fg_verified:
                return {
                    "call_id": "",
                    "success": True,
                    "target_hwnd": target_hwnd,
                    "foreground_verified": fg_verified,
                    "output": f"Successfully focused window: '{matched_title}' (Foreground Verified: {fg_verified})",
                    "error": None
                }
            else:
                return {
                    "call_id": "",
                    "success": False,
                    "target_hwnd": target_hwnd,
                    "foreground_verified": False,
                    "output": "",
                    "error": f"Failed to focus window: '{matched_title}' (blocked by Windows API)."
                }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": f"Error occurred during focus operation: {str(e)}"
            }


class TakeScreenshotTool(BaseTool):
    @property
    def name(self) -> str:
        return "take_screenshot"

    @property
    def description(self) -> str:
        return "Capture a visual screenshot and active window observation of the desktop."

    @property
    def category(self) -> str:
        return "windows"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {}
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from agent.core.vision import SCREEN_OBSERVER
        try:
            obs = SCREEN_OBSERVER.capture_observation()
            active_t = obs.get("active_window", {}).get("title", "Desktop") if obs.get("active_window") else "Desktop"
            msg = f"Screenshot captured. Active window: '{active_t}', Visual image available: {obs.get('image_available', False)}"
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
                "error": f"Failed to capture screenshot: {str(e)}"
            }
