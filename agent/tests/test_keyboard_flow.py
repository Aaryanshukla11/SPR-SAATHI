import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from agent.tools.computer import KeyboardTypeTool
from agent.tools import get_all_tools
from agent.core.action_validator import validate_action
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.control.takeover import TakeoverManager
from agent.core.executor import ToolExecutor
from agent.core.schema import get_tools_schema, get_compact_tools_schema
from agent.core import win32_utils

def test_keyboard_type_tool_properties():
    tool = KeyboardTypeTool()
    assert tool.name == "keyboard_type"
    assert tool.category == "keyboard"
    assert "text" in tool.parameters["properties"]
    assert "text" in tool.parameters["required"]
    assert "currently active window" in tool.description.lower()

def test_keyboard_type_tool_discovery():
    tools = get_all_tools()
    assert "keyboard_type" in tools
    tool = tools["keyboard_type"]
    assert isinstance(tool, KeyboardTypeTool)
    assert tool.name == "keyboard_type"
    assert tool.category == "keyboard"

def test_keyboard_type_action_validation():
    # Valid text
    is_valid, err = validate_action("keyboard_type", {"text": "Hello World"})
    assert is_valid is True
    assert err is None

    # Invalid empty text
    is_valid, err = validate_action("keyboard_type", {"text": ""})
    assert is_valid is False
    assert err is not None

    # Missing text key
    is_valid, err = validate_action("keyboard_type", {})
    assert is_valid is False
    assert err is not None

def test_keyboard_type_policy_management(tmp_path):
    cfg_file = os.path.join(tmp_path, "permissions_test.json")
    pm = PolicyManager(config_path=cfg_file)
    # Default policy for keyboard category
    assert pm.get_policy("keyboard_type", "keyboard", {"text": "test"}) == "prompt"

    # Override keyboard category to allow
    pm.update_policy("keyboard", "allow")
    assert pm.get_policy("keyboard_type", "keyboard", {"text": "test"}) == "allow"

    # Override keyboard category to deny
    pm.update_policy("keyboard", "deny")
    assert pm.get_policy("keyboard_type", "keyboard", {"text": "test"}) == "deny"

@pytest.mark.asyncio
async def test_keyboard_type_permission_and_executor(tmp_path):
    from agent.core.state import StateTracker
    cfg_file = os.path.join(tmp_path, "permissions_test.json")
    pm = PolicyManager(config_path=cfg_file)
    st = StateTracker()
    tm = TakeoverManager()
    broker = PermissionBroker(pm, st)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker, tm)

    # 1. Allow policy -> tool executes
    pm.update_policy("keyboard", "allow")
    res = await executor.execute_action("keyboard_type", {"text": "Hello"})
    assert res["success"] is True
    assert "Typed text: 'Hello'" in res["output"]

    # 2. Deny policy -> permission denied
    pm.update_policy("keyboard", "deny")
    res = await executor.execute_action("keyboard_type", {"text": "Hello"})
    assert res["success"] is False
    assert "Permission denied" in res["error"]

def test_keyboard_type_schema_generation():
    schemas = get_tools_schema()
    kb_schema = next((s for s in schemas if s["name"] == "keyboard_type"), None)
    assert kb_schema is not None
    assert "text" in kb_schema["parameters"]["properties"]

    compact_schema = get_compact_tools_schema()
    assert "keyboard_type" in compact_schema
    assert "text (string)" in compact_schema

def test_win32_type_text_chunking_and_unicode():
    # Verify type_text handles multi-line, long paragraphs, symbols, and Unicode without raising errors
    test_text = (
        "Shriram is a leading manufacturer in the industrial equipment sector.\n"
        "Testing symbols & quotes: \"Hello!\", it's a test (100% working & verified) -> [A, B, C].\r\n"
        "Testing Unicode: café, résumé, ñ, ü, Español, Deutsch, 🚀.\n"
        + ("Long paragraph text chunking test sentence. " * 30)
    )
    win32_utils.type_text(test_text, chunk_size=30)
    assert True

def test_win32_type_text_international_scripts():
    scripts = [
        "हेलो वर्ल्ड",
        "你好世界",
        "こんにちは",
        "مرحبا",
        "Hello 😀 🚀 ✨"
    ]
    for script in scripts:
        win32_utils.type_text(script, chunk_size=10)
    assert True

@pytest.mark.asyncio
async def test_single_tool_execution_guarantee(tmp_path):
    from agent.core.state import StateTracker
    cfg_file = os.path.join(tmp_path, "permissions_test.json")
    pm = PolicyManager(config_path=cfg_file)
    pm.update_policy("keyboard", "allow")
    st = StateTracker()
    tm = TakeoverManager()
    broker = PermissionBroker(pm, st)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker, tm)

    with patch("agent.core.win32_utils.type_text") as mock_type:
        res = await executor.execute_action("keyboard_type", {"text": "Exact Single Invocation"}, call_id="call_123")
        assert res["success"] is True
        # Verify type_text was invoked exactly ONCE with exact arguments and call_id
        mock_type.assert_called_once_with("Exact Single Invocation", call_id="call_123")

@pytest.mark.asyncio
async def test_executor_idempotency_prevents_duplicate_execution(tmp_path):
    from agent.core.state import StateTracker
    cfg_file = os.path.join(tmp_path, "permissions_test.json")
    pm = PolicyManager(config_path=cfg_file)
    pm.update_policy("keyboard", "allow")
    st = StateTracker()
    tm = TakeoverManager()
    broker = PermissionBroker(pm, st)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker, tm)

    with patch("agent.core.win32_utils.type_text") as mock_type:
        # First execution
        res1 = await executor.execute_action("keyboard_type", {"text": "Hello"}, call_id="duplicate_test_1")
        assert res1["success"] is True
        assert mock_type.call_count == 1

        # Second dispatch with identical call_id (e.g. from websocket replay or retry)
        res2 = await executor.execute_action("keyboard_type", {"text": "Hello"}, call_id="duplicate_test_1")
        assert res2["success"] is True
        assert res2.get("duplicate_dispatch_prevented") is True
        # Must NOT have invoked type_text a second time!
        assert mock_type.call_count == 1

def test_clipboard_preservation_and_tracing():
    from agent.core.keyboard_trace import KEYBOARD_TRACER
    KEYBOARD_TRACER.clear()
    
    # Test setting initial clipboard
    initial_text = "ORIGINAL_USER_CLIPBOARD_DATA_123"
    win32_utils.set_clipboard_text(initial_text)
    assert win32_utils.get_clipboard_text() == initial_text
    
    # Perform type_text with mock SendInput / hotkey to avoid sending keys to actual active window
    with patch("agent.core.win32_utils.send_input_keyboard"):
        win32_utils.type_text("INJECTED_AGENT_TEXT_456", call_id="trace_test_1")
        
    # Verify clipboard was restored back to original text
    restored_text = win32_utils.get_clipboard_text()
    assert restored_text == initial_text
    
    # Verify trace recorded
    traces = KEYBOARD_TRACER.get_traces_for_call_id("trace_test_1")
    assert len(traces) > 0
    completed = next((t for t in traces if t["type"] == "type_text_completed"), None)
    assert completed is not None
    assert completed["typing_path"] == "win32_clipboard_paste"
    assert completed["text_length"] == len("INJECTED_AGENT_TEXT_456")
    assert completed["clipboard_restored"] is True
