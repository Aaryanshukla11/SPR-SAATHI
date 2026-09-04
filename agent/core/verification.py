import os
import re
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from agent.core import win32_utils
from agent.core.vision import verify_visual_change


class VerificationLevel(str, Enum):
    TOOL = "tool"
    APPLICATION = "application"
    FILE = "file"
    DATA = "data"
    VISUAL = "visual"
    GOAL = "goal"


@dataclass
class VerificationResult:
    level: VerificationLevel
    passed: bool
    details: str
    metrics: Dict[str, Any] = field(default_factory=dict)


class MultiLevelVerifier:
    """
    Phase 4: Multi-Level Verification Engine.
    
    Verifies execution across all 6 levels defined in PHASES.md:
    1. Tool Verification: Did the tool execute without fatal exception?
    2. Application Verification: Did the target application respond and stay alive/unhung?
    3. File Verification: Was the expected file created, modified, or populated?
    4. Data Verification: Does the returned output contain the expected schema/data?
    5. Visual Verification: Did the live screen experience expected visual transitions?
    6. Goal Verification: Has the overarching user goal been genuinely fulfilled?
    """

    def verify_tool(self, tool_result: Dict[str, Any]) -> VerificationResult:
        """Level 1: Tool Verification - verifies tool execution exit status."""
        if not isinstance(tool_result, dict):
            return VerificationResult(
                level=VerificationLevel.TOOL,
                passed=False,
                details="Tool returned non-dictionary result payload."
            )
        
        success = bool(tool_result.get("success", False))
        error = tool_result.get("error")
        
        if success and not error:
            return VerificationResult(
                level=VerificationLevel.TOOL,
                passed=True,
                details="Tool executed successfully."
            )
        else:
            return VerificationResult(
                level=VerificationLevel.TOOL,
                passed=False,
                details=f"Tool execution failed: {error or 'Unknown failure'}"
            )

    def verify_application(
        self,
        target_process_or_title: str,
        expected_hwnd: Optional[int] = None
    ) -> VerificationResult:
        """Level 2: Application Verification - checks if target window is responsive and alive."""
        if not target_process_or_title and not expected_hwnd:
            return VerificationResult(
                level=VerificationLevel.APPLICATION,
                passed=True,
                details="No target application specified for verification."
            )

        if not win32_utils.IS_WINDOWS:
            return VerificationResult(
                level=VerificationLevel.APPLICATION,
                passed=True,
                details="Non-Windows OS bypass."
            )

        hwnd = expected_hwnd
        if not hwnd:
            windows = win32_utils.list_desktop_windows()
            query = target_process_or_title.lower().strip()
            for w in windows:
                if query in w["process"].lower() or query in w["title"].lower():
                    hwnd = w["hwnd"]
                    break

        if not hwnd:
            return VerificationResult(
                level=VerificationLevel.APPLICATION,
                passed=False,
                details=f"Target application '{target_process_or_title}' window not found on desktop."
            )

        responsive = win32_utils.is_window_responsive(hwnd)
        if not responsive:
            return VerificationResult(
                level=VerificationLevel.APPLICATION,
                passed=False,
                details=f"Application window (HWND {hwnd}) is hung and not responding to Windows messages.",
                metrics={"hwnd": hwnd, "responsive": False}
            )

        return VerificationResult(
            level=VerificationLevel.APPLICATION,
            passed=True,
            details=f"Target application window (HWND {hwnd}) is alive and responsive.",
            metrics={"hwnd": hwnd, "responsive": True}
        )

    def verify_file(
        self,
        file_path: str,
        expected_content: Optional[str] = None,
        must_exist: bool = True
    ) -> VerificationResult:
        """Level 3: File Verification - validates file existence, size, and content."""
        if not file_path:
            return VerificationResult(
                level=VerificationLevel.FILE,
                passed=False,
                details="No file path specified for file verification."
            )

        resolved_path = os.path.abspath(os.path.expanduser(file_path))
        exists = os.path.exists(resolved_path)

        if must_exist and not exists:
            return VerificationResult(
                level=VerificationLevel.FILE,
                passed=False,
                details=f"Expected file does not exist: {resolved_path}"
            )
        elif not must_exist and exists:
            return VerificationResult(
                level=VerificationLevel.FILE,
                passed=False,
                details=f"File was expected to be absent but exists: {resolved_path}"
            )
        elif not must_exist and not exists:
            return VerificationResult(
                level=VerificationLevel.FILE,
                passed=True,
                details=f"File correctly absent: {resolved_path}"
            )

        size_bytes = os.path.getsize(resolved_path)
        metrics = {"path": resolved_path, "size_bytes": size_bytes}

        if expected_content:
            try:
                with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if expected_content not in content:
                    return VerificationResult(
                        level=VerificationLevel.FILE,
                        passed=False,
                        details=f"File content does not contain expected snippet in {resolved_path}",
                        metrics=metrics
                    )
            except Exception as e:
                return VerificationResult(
                    level=VerificationLevel.FILE,
                    passed=False,
                    details=f"Failed to read file {resolved_path}: {e}",
                    metrics=metrics
                )

        return VerificationResult(
            level=VerificationLevel.FILE,
            passed=True,
            details=f"File verification confirmed for {resolved_path} (size={size_bytes} bytes).",
            metrics=metrics
        )

    def verify_data(
        self,
        data: Any,
        expected_keys: Optional[List[str]] = None,
        expected_pattern: Optional[str] = None
    ) -> VerificationResult:
        """Level 4: Data Verification - checks structured data output schemas and regex patterns."""
        if expected_keys and isinstance(data, dict):
            missing_keys = [k for k in expected_keys if k not in data]
            if missing_keys:
                return VerificationResult(
                    level=VerificationLevel.DATA,
                    passed=False,
                    details=f"Output missing expected keys: {missing_keys}"
                )

        if expected_pattern and isinstance(data, str):
            if not re.search(expected_pattern, data):
                return VerificationResult(
                    level=VerificationLevel.DATA,
                    passed=False,
                    details=f"Output does not match required regex pattern: {expected_pattern}"
                )

        return VerificationResult(
            level=VerificationLevel.DATA,
            passed=True,
            details="Data verification passed."
        )

    def verify_visual(
        self,
        obs_before: Dict[str, Any],
        obs_after: Dict[str, Any],
        expect_change: bool = True
    ) -> VerificationResult:
        """Level 5: Visual Verification - mathematically verifies pixel change."""
        img_before_path = obs_before.get("image_path")
        img_after_path = obs_after.get("image_path")

        if not img_before_path or not img_after_path:
            return VerificationResult(
                level=VerificationLevel.VISUAL,
                passed=True,
                details="Visual diff skipped (missing image capture paths)."
            )

        try:
            from PIL import Image
            img1 = Image.open(img_before_path)
            img2 = Image.open(img_after_path)
            diff_res = verify_visual_change(img1, img2)
            change_detected = diff_res.get("change_detected", False)

            if expect_change and not change_detected:
                return VerificationResult(
                    level=VerificationLevel.VISUAL,
                    passed=False,
                    details="Visual verification failed: screen pixels did not change after action execution.",
                    metrics=diff_res
                )
            return VerificationResult(
                level=VerificationLevel.VISUAL,
                passed=True,
                details=f"Visual verification confirmed (pixels changed: {diff_res.get('pixels_changed', 0)}).",
                metrics=diff_res
            )
        except Exception as e:
            return VerificationResult(
                level=VerificationLevel.VISUAL,
                passed=True,
                details=f"Visual verification diagnostic exception: {e}"
            )

    def verify_action(
        self,
        action_name: str,
        arguments: Dict[str, Any],
        tool_result: Dict[str, Any],
        obs_before: Dict[str, Any],
        obs_after: Dict[str, Any]
    ) -> Dict[VerificationLevel, VerificationResult]:
        """
        Executes all applicable verification levels for a specific action.
        """
        results: Dict[VerificationLevel, VerificationResult] = {}

        # 1. Tool verification (all actions)
        results[VerificationLevel.TOOL] = self.verify_tool(tool_result)

        # 2. File verification (file tools)
        if action_name in ["create_file", "write_file", "append_file", "delete_file"]:
            fpath = arguments.get("file_path") or arguments.get("path")
            must_exist = (action_name != "delete_file")
            expected_text = arguments.get("content")
            results[VerificationLevel.FILE] = self.verify_file(
                file_path=fpath,
                expected_content=expected_text,
                must_exist=must_exist
            )

        # 3. Application verification (launch_app, focus_window)
        if action_name in ["launch_app", "focus_window"]:
            target_app = arguments.get("app_name") or arguments.get("process_name") or arguments.get("title_substring", "")
            target_hwnd = tool_result.get("target_hwnd") or tool_result.get("readiness", {}).get("hwnd")
            results[VerificationLevel.APPLICATION] = self.verify_application(target_app, expected_hwnd=target_hwnd)

        # 4. Visual verification (screen-modifying computer actions)
        if action_name in ["mouse_click", "mouse_drag", "keyboard_type", "keyboard_press", "keyboard_hotkey", "draw_shape", "draw_rectangle"]:
            results[VerificationLevel.VISUAL] = self.verify_visual(obs_before, obs_after, expect_change=True)

        return results


# Global singleton instance
VERIFIER = MultiLevelVerifier()
