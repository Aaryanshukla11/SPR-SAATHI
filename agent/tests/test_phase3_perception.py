import pytest
import os
from unittest.mock import patch, MagicMock

from agent.core import win32_utils
from agent.core.perception import UnifiedPerceptionManager, UNIFIED_PERCEPTION


# ============================================================================
# 1. ACTIVE WINDOW & APPLICATION DETECTION TESTS
# ============================================================================

def test_active_window_detection():
    """Verify active window details extract title, process, HWND, and bounding boxes."""
    details = win32_utils.get_active_window_details()
    assert isinstance(details, dict)
    assert "hwnd" in details
    assert "title" in details
    assert "process" in details
    assert "bounds" in details


def test_application_metadata_extraction():
    """Verify application metadata extracts class name, PID, responsiveness, and styles."""
    active_win = win32_utils.get_active_window_details()
    hwnd = active_win.get("hwnd", 0)
    
    if hwnd:
        meta = win32_utils.get_application_metadata(hwnd)
        assert isinstance(meta, dict)
        assert meta["hwnd"] == hwnd
        assert "class_name" in meta
        assert "pid" in meta
        assert "is_responsive" in meta
        assert meta["is_responsive"] is True
    else:
        meta = win32_utils.get_application_metadata(0)
        assert meta == {}


# ============================================================================
# 2. WINDOW HIERARCHY & CHILD CONTROLS TESTS
# ============================================================================

def test_window_hierarchy_enumeration():
    """Verify get_window_hierarchy returns child controls with geometry and text."""
    active_win = win32_utils.get_active_window_details()
    hwnd = active_win.get("hwnd", 0)
    
    # Even if active window has no children or has children, it must return a list of dicts
    hierarchy = win32_utils.get_window_hierarchy(hwnd)
    assert isinstance(hierarchy, list)
    for ctrl in hierarchy:
        assert "hwnd" in ctrl
        assert "class_name" in ctrl
        assert "bounds" in ctrl
        assert "visible" in ctrl


def test_mock_window_hierarchy_structure():
    """Verify hierarchy parsing with mock child controls."""
    fake_children = [
        {
            "hwnd": 5001,
            "class_name": "Edit",
            "text": "File editor text",
            "visible": True,
            "control_id": 15,
            "bounds": {"x": 100, "y": 150, "width": 800, "height": 600}
        },
        {
            "hwnd": 5002,
            "class_name": "Button",
            "text": "Save",
            "visible": True,
            "control_id": 16,
            "bounds": {"x": 920, "y": 150, "width": 80, "height": 30}
        }
    ]

    with patch("agent.core.win32_utils.get_window_hierarchy", return_value=fake_children):
        mgr = UnifiedPerceptionManager()
        snapshot = mgr.capture_unified_perception(include_image=False)
        assert len(snapshot["window_hierarchy"]) == 2
        assert snapshot["window_hierarchy"][1]["text"] == "Save"


# ============================================================================
# 3. RUNNING PROCESSES DETECTION TESTS
# ============================================================================

def test_running_processes_detection():
    """Verify get_running_processes returns active processes sorted by memory."""
    procs = win32_utils.get_running_processes(limit=10)
    assert isinstance(procs, list)
    assert len(procs) > 0
    for p in procs:
        assert "pid" in p
        assert "name" in p
        assert "memory_mb" in p
        assert p["memory_mb"] >= 0


# ============================================================================
# 4. FILE-SYSTEM STATE TRACKING TESTS
# ============================================================================

def test_file_system_state_tracking(tmp_path):
    """Verify get_file_system_state discovers workspace directory and recently modified files."""
    mgr = UnifiedPerceptionManager()
    
    # Create temporary files
    f1 = tmp_path / "test_doc.txt"
    f1.write_text("Hello SPR SAATHI")
    
    state = mgr.get_file_system_state(root_dir=str(tmp_path))
    assert state["working_directory"] == str(tmp_path)
    assert len(state["recent_workspace_files"]) >= 1
    assert state["recent_workspace_files"][0]["name"] == "test_doc.txt"


# ============================================================================
# 5. BROWSER STATE DETECTION TESTS
# ============================================================================

def test_browser_state_detection_with_browser():
    """Verify get_browser_state parses tab title and browser metadata when browser is active."""
    mock_active = {
        "hwnd": 9999,
        "title": "Google Search - Google Chrome",
        "process": "chrome.exe"
    }
    with patch("agent.core.win32_utils.get_active_window_details", return_value=mock_active), \
         patch("agent.core.win32_utils.IS_WINDOWS", True):
        bstate = win32_utils.get_browser_state(9999)
        assert bstate is not None
        assert bstate["is_browser"] is True
        assert bstate["browser_name"] == "Google Chrome"
        assert bstate["tab_title"] == "Google Search"


def test_browser_state_detection_with_non_browser():
    """Verify get_browser_state returns None when non-browser app is active."""
    mock_active = {
        "hwnd": 8888,
        "title": "Untitled - Notepad",
        "process": "notepad.exe"
    }
    with patch("agent.core.win32_utils.get_active_window_details", return_value=mock_active), \
         patch("agent.core.win32_utils.IS_WINDOWS", True):
        bstate = win32_utils.get_browser_state(8888)
        assert bstate is None


# ============================================================================
# 6. PERCEPTION PRIORITY HIERARCHY RESOLUTION TESTS
# ============================================================================

def test_priority_hierarchy_resolves_child_control_first():
    """Verify resolve_element_by_priority picks child controls (Priority 1) before window metadata."""
    fake_snapshot = {
        "window_hierarchy": [
            {
                "hwnd": 101,
                "class_name": "Button",
                "text": "Submit",
                "visible": True,
                "control_id": 1,
                "bounds": {"x": 300, "y": 400, "width": 100, "height": 40}
            }
        ],
        "visible_windows": [
            {"hwnd": 202, "title": "Submit Order Form", "process": "app.exe", "bounds": {"x": 100, "y": 100, "width": 600, "height": 500}}
        ],
        "browser_state": None
    }

    mgr = UnifiedPerceptionManager()
    resolved = mgr.resolve_element_by_priority("Submit", fake_snapshot)
    assert resolved is not None
    assert resolved["source_priority"] == 1
    assert resolved["target_type"] == "control"
    assert resolved["center"] == {"x": 350, "y": 420}


def test_priority_hierarchy_falls_back_to_browser_state():
    """Verify resolve_element_by_priority falls back to browser tab when control is absent."""
    fake_snapshot = {
        "window_hierarchy": [],
        "browser_state": {
            "is_browser": True,
            "browser_name": "Microsoft Edge",
            "tab_title": "GitHub Dashboard"
        },
        "active_window": {
            "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080}
        },
        "visible_windows": []
    }

    mgr = UnifiedPerceptionManager()
    resolved = mgr.resolve_element_by_priority("GitHub", fake_snapshot)
    assert resolved is not None
    assert resolved["source_priority"] == 2
    assert resolved["target_type"] == "browser_tab"


def test_priority_hierarchy_falls_back_to_window_metadata():
    """Verify resolve_element_by_priority falls back to visible window list when control & browser tab absent."""
    fake_snapshot = {
        "window_hierarchy": [],
        "browser_state": None,
        "visible_windows": [
            {"hwnd": 777, "title": "Calculator", "process": "calculator.exe", "bounds": {"x": 500, "y": 300, "width": 400, "height": 500}}
        ]
    }

    mgr = UnifiedPerceptionManager()
    resolved = mgr.resolve_element_by_priority("Calculator", fake_snapshot)
    assert resolved is not None
    assert resolved["source_priority"] == 3
    assert resolved["target_type"] == "window"
    assert resolved["center"] == {"x": 700, "y": 550}


# ============================================================================
# 7. ENVIRONMENT CHANGE DETECTION TESTS
# ============================================================================

def test_environment_change_detection():
    """Verify detect_environment_changes flags window transitions and process count deltas."""
    mgr = UnifiedPerceptionManager()

    before = {
        "active_window": {"hwnd": 111, "title": "Notepad"},
        "running_processes": [{"pid": 10}, {"pid": 20}],
        "visual_observation": {}
    }
    after = {
        "active_window": {"hwnd": 222, "title": "Paint"},
        "running_processes": [{"pid": 10}, {"pid": 20}, {"pid": 30}],
        "visual_observation": {}
    }

    changes = mgr.detect_environment_changes(before, after)
    assert changes["window_switched"] is True
    assert changes["new_processes_count"] == 1
    assert changes["terminated_processes_count"] == 0
