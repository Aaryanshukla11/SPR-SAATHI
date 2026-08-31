import subprocess
import os
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
            # Try launching
            # Expand environment variables like %SystemRoot%
            expanded_name = os.path.expandvars(app_name)
            if hasattr(os, "startfile"):
                try:
                    os.startfile(expanded_name)
                except Exception:
                    subprocess.Popen(expanded_name, shell=True)
            else:
                subprocess.Popen(expanded_name, shell=True)
            import time
            time.sleep(1.0)
            msg = f"Application '{app_name}' launched successfully."
            return {
                "call_id": "",
                "success": True,
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
            if focused:
                return {
                    "call_id": "",
                    "success": True,
                    "output": f"Successfully focused window: '{matched_title}'",
                    "error": None
                }
            else:
                return {
                    "call_id": "",
                    "success": False,
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
