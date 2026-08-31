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
    
    # Missing tool_name in tool_call
    ok, err = validate_model_decision({"decision_type": "tool_call", "arguments": {"app_name": "notepad.exe"}})
    assert ok is False
    assert "Missing 'tool_name'" in err
    
    # Missing arguments in tool_call
    ok, err = validate_model_decision({"decision_type": "tool_call", "tool_name": "launch_app"})
    assert ok is False
    assert "Missing 'arguments'" in err

    # Malformed arguments (None or missing)
    ok, err = validate_model_decision({"decision_type": "tool_call", "tool_name": "launch_app", "arguments": None})
    assert ok is False
    assert "Missing 'arguments'" in err

    # Invalid final (missing message)
    ok, err = validate_model_decision({"decision_type": "final"})
    assert ok is False
    assert "Missing 'message'" in err

    # Invalid wait (missing duration_seconds)
    ok, err = validate_model_decision({"decision_type": "wait"})
    assert ok is False
    assert "Missing 'duration_seconds'" in err

    # Invalid wait (negative duration)
    ok, err = validate_model_decision({"decision_type": "wait", "duration_seconds": -1.0})
    assert ok is False
    assert "must be positive" in err

    # Invalid wait (non-numeric duration)
    ok, err = validate_model_decision({"decision_type": "wait", "duration_seconds": "invalid"})
    assert ok is False
    assert "must be a valid number" in err

    # Invalid ask_user (missing question)
    ok, err = validate_model_decision({"decision_type": "ask_user"})
    assert ok is False
    assert "Missing 'question'" in err

    # Invalid replan (missing reason)
    ok, err = validate_model_decision({"decision_type": "replan"})
    assert ok is False
    assert "Missing 'reason'" in err

# --- Model Provider Integration and Switching Tests ---

@pytest.mark.asyncio
async def test_provider_decisions_switching():
    # Both api and local providers must implement the decide_action interface returning identical outcomes
    api_model = ApiModelProvider("Gemini 3.5 Flash", config={"api_key": "fake_key"})
    local_model = LocalModelProvider("Llama 3 8B")
    
    obs = {
        "active_window": {"title": "Desktop", "process": ""},
        "visible_windows": [],
        "screen": {"width": 1920, "height": 1080},
        "cursor": {"x": 0, "y": 0}
    }
    
    import json
    mock_response_json = {
        "message": {
            "content": '{"decision_type": "tool_call", "tool_name": "launch_app", "arguments": {"app_name": "notepad.exe"}}'
        },
        "choices": [
            {
                "message": {
                    "content": '{"decision_type": "tool_call", "tool_name": "launch_app", "arguments": {"app_name": "notepad.exe"}}'
                }
            }
        ],
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"decision_type": "tool_call", "tool_name": "launch_app", "arguments": {"app_name": "notepad.exe"}}'
                        }
                    ]
                }
            }
        ]
    }
    
    mock_tags_json = {
        "models": [
            {"name": "qwen2.5-coder:latest"},
            {"name": "qwen2.5-coder:7b"}
        ]
    }
    
    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data
            
        def json(self):
            return self._json_data
            
        @property
        def text(self):
            return json.dumps(self._json_data)

    mock_client = MagicMock()
    
    async def mock_get(url, **kwargs):
        if "tags" in url:
            return MockResponse(200, mock_tags_json)
        return MockResponse(200, {})
        
    async def mock_post(url, **kwargs):
        return MockResponse(200, mock_response_json)
        
    mock_client.get = mock_get
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("urllib.request.urlopen") as mock_urlopen:
         
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(mock_tags_json).encode()
        
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
    assert pm.get_policy("launch_app", "applications", {"app_name": "notepad.exe"}) == "prompt"
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

def test_clean_and_normalize_decision():
    from agent.models.base import clean_and_normalize_decision
    
    # Test 1: standard clean JSON
    json_str = '{"decision_type": "tool_call", "tool_name": "launch_app", "arguments": {"app_name": "notepad"}}'
    dec = clean_and_normalize_decision(json_str)
    assert dec["decision_type"] == "tool_call"
    assert dec["tool_name"] == "launch_app"
    assert dec["arguments"] == {"app_name": "notepad"}

    # Test 2: JSON with markdown code blocks
    markdown_str = '```json\n{"decision_type": "final", "message": "Success!"}\n```'
    dec = clean_and_normalize_decision(markdown_str)
    assert dec["decision_type"] == "final"
    assert dec["message"] == "Success!"

    # Test 3: JSON with alternative keys
    alt_str = '{"type": "tool_call", "name": "focus_window", "args": {"title": "Notepad"}}'
    dec = clean_and_normalize_decision(alt_str)
    assert dec["decision_type"] == "tool_call"
    assert dec["tool_name"] == "focus_window"
    assert dec["arguments"] == {"title": "Notepad"}

    # Test 4: Wait command key normalization
    wait_str = '{"type": "wait", "duration": 5.0}'
    dec = clean_and_normalize_decision(wait_str)
    assert dec["decision_type"] == "wait"
    assert dec["duration_seconds"] == 5.0

# --- Architectural Verification Tests (Requirement A to I) ---

@pytest.mark.asyncio
async def test_architectural_planner_no_computer_actions():
    """Test A: Planner does not choose concrete computer actions"""
    planner = RuleBasedPlanner(None)
    
    # Verify create_high_level_plan does not select computer actions
    high_level = planner.create_high_level_plan("Open Paint and draw a house")
    assert len(high_level) > 0
    for step in high_level:
        assert step.get("tool_call") is None
        
    # Verify create_plan does not select computer actions (returns empty list)
    steps_desc, tool_calls = await planner.create_plan("Open Notepad", "")
    assert len(tool_calls) == 0

@pytest.mark.asyncio
async def test_architectural_providers_no_emulation():
    """Test B: Provider does not manufacture task-specific actions"""
    # Verify neither provider has hardcoded/manufactured fallbacks or emulation dictionaries
    api_model = ApiModelProvider("Gemini 3.5 Flash", config={})
    local_model = LocalModelProvider("Llama 3 8B")
    
    obs = {"active_window": None, "visible_windows": [], "screen": {"width": 100, "height": 100}, "cursor": {"x": 0, "y": 0}}
    
    # ApiModelProvider with missing keys should raise exception rather than return a fake decision
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError) as exc_info:
            await api_model.decide_action("Open Notepad", [], obs, [])
        assert "API_CREDENTIALS_MISSING" in str(exc_info.value) or "API local service call failed" in str(exc_info.value)
        
    # LocalModelProvider when Ollama is down should raise exception rather than return a fake decision
    with pytest.raises(RuntimeError) as exc_info:
        await local_model.decide_action("Draw a house in Paint", [], obs, [])
    assert "MODEL_UNAVAILABLE" in str(exc_info.value)

@pytest.mark.asyncio
async def test_architectural_local_unavailable_ollama():
    """Test C: Unavailable Ollama returns an explicit error"""
    local_model = LocalModelProvider("Llama 3 8B")
    obs = {"active_window": None, "visible_windows": [], "screen": {"width": 100, "height": 100}, "cursor": {"x": 0, "y": 0}}
    
    # Mocking httpx connection failure to simulate Ollama down
    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
        with pytest.raises(RuntimeError) as exc_info:
            await local_model.decide_action("Open Paint", [], obs, [])
        assert "MODEL_UNAVAILABLE" in str(exc_info.value)

@pytest.mark.asyncio
async def test_architectural_api_credentials_missing():
    """Test D: Unavailable API credentials return an explicit error"""
    api_model = ApiModelProvider("Gemini 3.5 Flash", config={})
    obs = {"active_window": None, "visible_windows": [], "screen": {"width": 100, "height": 100}, "cursor": {"x": 0, "y": 0}}
    
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError) as exc_info:
            await api_model.decide_action("Open Notepad", [], obs, [])
        assert "API_CREDENTIALS_MISSING" in str(exc_info.value) or "API local service call failed" in str(exc_info.value)

def test_architectural_tool_schema_exposed():
    """Test E: Tool schemas are available to the model gateway"""
    from agent.core.schema import get_tools_schema
    schemas = get_tools_schema()
    
    assert len(schemas) > 0
    for s in schemas:
        assert "name" in s
        assert "description" in s
        assert "parameters" in s
        assert "properties" in s["parameters"]

def test_architectural_tool_results_history():
    """Test F: Tool results can be represented as model context"""
    tracker = StateTracker()
    tracker.reset("Test Goal")
    
    tracker.add_action_history(
        action_name="launch_app",
        parameters={"app_name": "notepad.exe"},
        status="completed",
        error_message=None,
        duration_ms=150,
        output="Application launched successfully"
    )
    
    assert len(tracker.action_history) == 1
    item = tracker.action_history[0]
    assert item["action"] == "launch_app"
    assert item["parameters"] == {"app_name": "notepad.exe"}
    assert item["status"] == "completed"
    assert item["duration_ms"] == 150
    assert item["output"] == "Application launched successfully"

@pytest.mark.asyncio
async def test_architectural_permission_enforcement(temp_config_path):
    """Test G: Permission remains enforced"""
    pm = PolicyManager(config_path=temp_config_path)
    broker = PermissionBroker(pm)
    pm.update_policy("terminal", "deny")
    
    # cmd tool is in terminal category and terminal category is denied
    allowed = await broker.check_permission("cmd", "terminal", {"command": "echo hello"})
    assert allowed is False
    assert broker.audit_trail[0]["decision"] == "deny"

@pytest.mark.asyncio
async def test_architectural_takeover_pauses_execution():
    """Test H: Takeover pauses execution"""
    from agent.control.takeover import TakeoverManager
    tm = TakeoverManager()
    
    # Trigger takeover
    tm.take_control()
    assert tm.is_takeover_active is True
    
    # Test that executor blocks tool execution
    pm = PolicyManager()
    broker = PermissionBroker(pm)
    executor = ToolExecutor(get_all_tools(), broker, tm)
    
    res = await executor.execute_action("launch_app", {"app_name": "notepad.exe"})
    assert res["success"] is False
    assert res["error"] == "CONTROL_LOCKED"

@pytest.mark.asyncio
async def test_architectural_stop_releases_buttons():
    """Test I: Stop cancels execution and releases held buttons"""
    tracker = StateTracker()
    pm = PolicyManager()
    broker = PermissionBroker(pm)
    executor = ToolExecutor(get_all_tools(), broker)
    
    from agent.control.takeover import TakeoverManager
    tm = TakeoverManager()
    
    loop = AgentLoop(
        state_tracker=tracker,
        planner=RuleBasedPlanner(None),
        executor=executor,
        takeover_manager=tm
    )
    
    with patch("agent.core.win32_utils.release_all_buttons") as mock_release:
        loop.stop_task()
        assert tracker.status == "cancelled"
        mock_release.assert_called_once()

