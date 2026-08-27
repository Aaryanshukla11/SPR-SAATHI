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
from agent.core.action_validator import validate_action

# --- Fixtures ---

@pytest.fixture
def temp_config_path():
    """Create a temporary config file path for testing persistence."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture(autouse=True)
def mock_win32_utils():
    """Mock win32_utils calls to avoid actual hardware clicks during tests."""
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
            "title": "Untitled - Paint",
            "process": "mspaint.exe",
            "pid": 1234,
            "bounds": {"x": 200, "y": 100, "width": 800, "height": 600}
        }
        
        mock_list.return_value = [
            {
                "hwnd": 12345,
                "title": "Untitled - Paint",
                "process": "mspaint.exe",
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

# --- Policies Precedence and Persistence Tests ---

def test_policy_manager_defaults(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    # Conservative defaults check
    assert pm.get_policy("mouse_click", "mouse", {}) == "prompt"
    assert pm.get_policy("keyboard_type", "keyboard", {}) == "prompt"
    assert pm.get_policy("launch_app", "applications", {}) == "prompt"
    assert pm.get_policy("cmd", "terminal", {}) == "deny"
    assert pm.get_policy("powershell", "powershell", {}) == "deny"

def test_policy_manager_precedence(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    
    # 1. Category Scope override
    pm.update_policy("mouse", "allow")
    assert pm.get_policy("mouse_click", "mouse", {}) == "allow"
    
    # 2. Specific Application override matches: Notepad.exe is DENY by default
    assert pm.get_policy("launch_app", "applications", {"app_name": "notepad.exe"}) == "deny"
    
    # Custom specific application override matches
    pm.update_app_policy("discord.exe", "allow")
    assert pm.get_policy("launch_app", "applications", {"app_name": "discord.exe"}) == "allow"
    
    # Overrides win over category settings
    pm.update_policy("applications", "deny")
    assert pm.get_policy("launch_app", "applications", {"app_name": "discord.exe"}) == "allow"

def test_policy_manager_persistence(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    pm.update_policy("powershell", "allow")
    pm.update_app_policy("slack.exe", "deny")
    
    # Reload and assert settings persist
    pm2 = PolicyManager(config_path=temp_config_path)
    assert pm2.get_policy("powershell", "powershell", {}) == "allow"
    assert pm2.get_policy("launch_app", "applications", {"app_name": "slack.exe"}) == "deny"

# --- Permission Broker Tests ---

@pytest.mark.asyncio
async def test_broker_check_allow_deny(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    broker = PermissionBroker(pm)
    
    # ALLOW check
    pm.update_policy("browser", "allow")
    allowed = await broker.check_permission("open_browser_url", "browser", {})
    assert allowed is True
    assert len(broker.audit_trail) == 1
    assert broker.audit_trail[0]["decision"] == "allow"
    
    # DENY check
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
        # Resolve it async
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
    broker.timeout_seconds = 0.1 # short timeout for testing
    
    async def mock_slow_prompt(req_id, tool, args):
        # Do not resolve it, simulate slow user response
        await asyncio.sleep(0.5)
        
    broker.on_prompt_callback = mock_slow_prompt
    allowed = await broker.check_permission("mouse_click", "mouse", {"x": 100, "y": 100})
    # Timeout resolves to deny
    assert allowed is False
    assert broker.audit_trail[0]["decision"] == "timeout_deny"

@pytest.mark.asyncio
async def test_broker_check_cancellation(temp_config_path):
    pm = PolicyManager(config_path=temp_config_path)
    broker = PermissionBroker(pm)
    pm.update_policy("keyboard", "prompt")
    
    async def mock_keyboard_prompt(req_id, tool, args):
        # Trigger async loop stop / cancel
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
    
    # 1. Terminals check (cmd category is 'terminal')
    pm.update_policy("terminal", "allow")
    pm.update_policy("powershell", "deny")
    
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker)
    
    cmd_res = await executor.execute_action("cmd", {"command": "echo Hello"})
    assert cmd_res["success"] is True
    
    # 2. PowerShell check (powershell category is 'powershell')
    pwsh_res = await executor.execute_action("powershell", {"script": "Write-Output Hello"})
    assert pwsh_res["success"] is False
    assert "Permission denied" in pwsh_res["error"]
