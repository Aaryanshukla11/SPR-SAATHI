import pytest
import asyncio
import os
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock

from agent.core.state import StateTracker
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.core.executor import ToolExecutor
from agent.core.planner import RuleBasedPlanner
from agent.core.loop import AgentLoop
from agent.tools import get_all_tools
from agent.core import win32_utils
from agent.models.base import validate_model_decision, ModelDecision
from agent.models.api import ApiModelProvider
from agent.models.local import LocalModelProvider

# --- Fixtures ---

@pytest.fixture
def temp_config_path():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture(autouse=True)
def mock_win32_utils():
    with patch("agent.core.win32_utils.IS_WINDOWS", False), \
         patch("agent.core.win32_utils.get_active_window_details") as mock_active, \
         patch("agent.core.win32_utils.list_desktop_windows") as mock_list, \
         patch("agent.core.win32_utils.focus_window") as mock_focus, \
         patch("agent.core.win32_utils.type_text") as mock_type, \
         patch("agent.core.win32_utils.press_key") as mock_press, \
         patch("agent.core.win32_utils.hotkey") as mock_hotkey, \
         patch("agent.core.win32_utils.mouse_move") as mock_move, \
         patch("agent.core.win32_utils.mouse_down") as mock_down, \
         patch("agent.core.win32_utils.mouse_up") as mock_up, \
         patch("agent.core.win32_utils.mouse_drag") as mock_drag, \
         patch("agent.core.win32_utils.release_all_buttons") as mock_release, \
         patch("agent.core.win32_utils.get_screen_size", return_value=(1920, 1080)):
         
        mock_active.return_value = {
            "hwnd": 12345,
            "title": "Untitled - Notepad",
            "process": "notepad.exe",
            "pid": 1234,
            "bounds": {"x": 200, "y": 100, "width": 800, "height": 600}
        }
        
        mock_list.return_value = [
            {
                "hwnd": 12345,
                "title": "Untitled - Notepad",
                "process": "notepad.exe",
                "pid": 1234,
                "bounds": {"x": 200, "y": 100, "width": 800, "height": 600}
            }
        ]
        mock_focus.return_value = True
        
        yield {
            "active": mock_active,
            "list": mock_list,
            "focus": mock_focus,
            "type": mock_type,
            "press": mock_press,
            "hotkey": mock_hotkey,
            "move": mock_move,
            "down": mock_down,
            "up": mock_up,
            "drag": mock_drag,
            "release": mock_release
        }

# --- Decision Protocol Schema Validation Tests (Requirement 3 & 4) ---

def test_decision_protocol_validations():
    # Valid Cases
    ok, err = validate_model_decision({"decision_type": "tool_call", "tool_name": "launch_app", "arguments": {"app_name": "notepad.exe"}})
    assert ok is True
    
    ok, err = validate_model_decision({"decision_type": "final", "message": "Done"})
    assert ok is True
    
    ok, err = validate_model_decision({"decision_type": "replan", "reason": "stuck"})
    assert ok is True
    
    ok, err = validate_model_decision({"decision_type": "ask_user", "question": "Are you sure?"})
    assert ok is True
    
    ok, err = validate_model_decision({"decision_type": "wait", "duration_seconds": 2.5})
    assert ok is True

    # Invalid Cases
    ok, err = validate_model_decision({"decision_type": "unknown_type"})
    assert ok is False
    assert "Invalid decision type" in err
    
    ok, err = validate_model_decision({"decision_type": "tool_call", "tool_name": "launch_app"})
    assert ok is False
    assert "Missing 'arguments'" in err

    ok, err = validate_model_decision({"decision_type": "wait", "duration_seconds": -1.0})
    assert ok is False
    assert "must be positive" in err

# --- Model Provider Integration and Switching Tests ---

@pytest.mark.asyncio
async def test_provider_decisions_switching():
    # Both api and local providers must implement the decide_action interface returning identical outcomes
    api_model = ApiModelProvider("Gemini 3.5 Flash")
    local_model = LocalModelProvider("Llama 3 8B")
    
    obs = {
        "active_window": {"title": "Desktop", "process": ""},
        "visible_windows": [],
        "screen": {"width": 1920, "height": 1080},
        "cursor": {"x": 0, "y": 0}
    }
    
    # Notepad closed observation -> both should decide to launch Notepad
    api_dec = await api_model.decide_action("Open Notepad and type Hello", [], obs, [])
    local_dec = await local_model.decide_action("Open Notepad and type Hello", [], obs, [])
    
    assert api_dec["decision_type"] == "tool_call"
    assert api_dec["tool_name"] == "launch_app"
    assert api_dec["arguments"] == {"app_name": "notepad.exe"}
    
    assert local_dec["decision_type"] == "tool_call"
    assert local_dec["tool_name"] == "launch_app"
    assert local_dec["arguments"] == {"app_name": "notepad.exe"}

# --- Policies Precedence and Persistence Tests ---

def test_policy_manager_defaults(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    assert pm.get_policy("mouse_click", "mouse", {}) == "prompt"
    assert pm.get_policy("keyboard_type", "keyboard", {}) == "prompt"
    assert pm.get_policy("launch_app", "applications", {}) == "prompt"
    assert pm.get_policy("cmd", "terminal", {}) == "deny"
    assert pm.get_policy("powershell", "powershell", {}) == "deny"

def test_policy_manager_precedence(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    pm.update_policy("mouse", "allow")
    assert pm.get_policy("mouse_click", "mouse", {}) == "allow"
    assert pm.get_policy("launch_app", "applications", {"app_name": "notepad.exe"}) == "deny"
    pm.update_app_policy("discord.exe", "allow")
    assert pm.get_policy("launch_app", "applications", {"app_name": "discord.exe"}) == "allow"
    pm.update_policy("applications", "deny")
    assert pm.get_policy("launch_app", "applications", {"app_name": "discord.exe"}) == "allow"

def test_policy_manager_persistence(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    pm.update_policy("powershell", "allow")
    pm.update_app_policy("slack.exe", "deny")
    
    pm2 = PolicyManager(config_path=temp_config_path)
    assert pm2.get_policy("powershell", "powershell", {}) == "allow"
    assert pm2.get_policy("launch_app", "applications", {"app_name": "slack.exe"}) == "deny"

# --- Permission Broker Tests ---

@pytest.mark.asyncio
async def test_broker_check_allow_deny(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    broker = PermissionBroker(pm)
    pm.update_policy("browser", "allow")
    allowed = await broker.check_permission("open_browser_url", "browser", {})
    assert allowed is True
    assert len(broker.audit_trail) == 1
    assert broker.audit_trail[0]["decision"] == "allow"
    
    pm.update_policy("terminal", "deny")
    allowed = await broker.check_permission("cmd", "terminal", {})
    assert allowed is False
    assert len(broker.audit_trail) == 2
    assert broker.audit_trail[1]["decision"] == "deny"

@pytest.mark.asyncio
async def test_broker_check_prompt_resolve(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    broker = PermissionBroker(pm)
    pm.update_policy("filesystem", "prompt")
    
    prompted = False
    async def mock_prompt(req_id, tool, args):
        nonlocal prompted
        prompted = True
        broker.resolve_permission(req_id, "allow")
        
    broker.on_prompt_callback = mock_prompt
    allowed = await broker.check_permission("create_file", "filesystem", {})
    assert prompted is True
    assert allowed is True

@pytest.mark.asyncio
async def test_broker_check_timeout(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    broker = PermissionBroker(pm)
    pm.update_policy("mouse", "prompt")
    broker.timeout_seconds = 0.1
    
    async def mock_slow_prompt(req_id, tool, args):
        await asyncio.sleep(0.5)
        
    broker.on_prompt_callback = mock_slow_prompt
    allowed = await broker.check_permission("mouse_click", "mouse", {"x": 100, "y": 100})
    assert allowed is False
    assert broker.audit_trail[0]["decision"] == "timeout_deny"

@pytest.mark.asyncio
async def test_broker_check_cancellation(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    broker = PermissionBroker(pm)
    pm.update_policy("keyboard", "prompt")
    
    async def mock_keyboard_prompt(req_id, tool, args):
        asyncio.get_running_loop().call_later(0.1, broker.cancel_all_pending)
        
    broker.on_prompt_callback = mock_keyboard_prompt
    with pytest.raises(asyncio.CancelledError):
        await broker.check_permission("keyboard_type", "keyboard", {"text": "hello"})
        
    assert broker.audit_trail[0]["decision"] == "cancelled_deny"

# --- Separate Scopes Tool Execution Checks ---

@pytest.mark.asyncio
async def test_separate_scopes_routing(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    broker = PermissionBroker(pm)
    pm.update_policy("terminal", "allow")
    pm.update_policy("powershell", "deny")
    
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker)
    
    cmd_res = await executor.execute_action("cmd", {"command": "echo Hello"})
    assert cmd_res["success"] is True
    
    pwsh_res = await executor.execute_action("powershell", {"script": "Write-Output Hello"})
    assert pwsh_res["success"] is False
    assert "Permission denied" in pwsh_res["error"]

def test_health_check_endpoint():
    from fastapi.testclient import TestClient
    from agent.main import app
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
