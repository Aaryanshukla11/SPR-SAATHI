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
        res = await executor.execute_action("keyboard_type", {"text": "Exact Single Invocation"})
        assert res["success"] is True
        # Verify type_text was invoked exactly ONCE with exact arguments
        mock_type.assert_called_once_with("Exact Single Invocation")

def test_partial_injection_detection():
    # Mock SendInput to simulate partial event injection on fallback path
    with patch("agent.core.win32_utils.set_clipboard_text", return_value=False):
        with patch("ctypes.windll.user32.SendInput", return_value=1):
            with pytest.raises(RuntimeError) as exc_info:
                win32_utils.type_text("Test", chunk_size=10)
            assert "partial injection failure" in str(exc_info.value)
