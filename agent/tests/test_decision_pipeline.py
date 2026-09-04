import pytest
import json
from agent.models.base import (
    validate_model_decision, clean_and_normalize_decision,
    safe_parse_api_json, ModelPipelineError, ModelEmptyResponseError,
    ModelApiJsonError, ModelDecisionParseError
)
from agent.core.layman_formatter import format_layman_action, format_layman_decision


class TestLayer1ApiResponseValidation:
    """Tests Layer 1 HTTP/API response handling and error isolation."""

    def test_empty_http_body_raises_empty_response_error(self):
        with pytest.raises(ModelEmptyResponseError) as exc:
            safe_parse_api_json("", endpoint="http://127.0.0.1:11434/api/chat", status_code=200)
        assert "Empty HTTP response body" in str(exc.value)

    def test_whitespace_only_http_body_raises_empty_response_error(self):
        with pytest.raises(ModelEmptyResponseError) as exc:
            safe_parse_api_json("   \n\t  ", endpoint="http://127.0.0.1:11434/api/chat", status_code=200)
        assert "Empty HTTP response body" in str(exc.value)

    def test_html_error_page_raises_api_json_error(self):
        html = "<!DOCTYPE html><html><head><title>502 Bad Gateway</title></head><body>Bad Gateway</body></html>"
        with pytest.raises(ModelApiJsonError) as exc:
            safe_parse_api_json(html, endpoint="http://proxy/api", status_code=502)
        assert "Failed to parse API JSON" in str(exc.value)
        assert "502" in str(exc.value)

    def test_valid_api_json_parses_successfully(self):
        raw = '{"message": {"role": "assistant", "content": "{\\"type\\": \\"tool_call\\"}"}}'
        data = safe_parse_api_json(raw, endpoint="http://127.0.0.1:11434/api/chat", status_code=200)
        assert "message" in data
        assert data["message"]["role"] == "assistant"


class TestLayer2DecisionParsingAndNormalization:
    """Tests Layer 2 model decision parsing, markdown unwrapping, and legacy normalization."""

    def test_empty_model_output_raises_decision_parse_error(self):
        with pytest.raises(ModelDecisionParseError) as exc:
            clean_and_normalize_decision("")
        assert "Model returned an empty response" in str(exc.value)

    def test_plain_conversational_text_raises_decision_parse_error_safely(self):
        text = "Sure! I will open Paint and draw a portrait of Mahatma Gandhi for you right now."
        with pytest.raises(ModelDecisionParseError) as exc:
            clean_and_normalize_decision(text)
        assert "Model returned plain text or unparseable output" in str(exc.value)
        # Verify it provides a snippet and does NOT throw an unhandled char 0 crash
        assert "Sure! I will open Paint" in str(exc.value)

    def test_truncated_json_detected(self):
        truncated = '{"decision_type": "tool_call", "tool_name": "launch_app", "arguments": {"name": "mspaint.exe"'
        with pytest.raises(ModelDecisionParseError) as exc:
            clean_and_normalize_decision(truncated)
        assert "truncated or incomplete" in str(exc.value)

    def test_markdown_code_fences_parsed_cleanly(self):
        md = """Here is your next action:
```json
{
    "decision_type": "tool_call",
    "tool_name": "launch_app",
    "arguments": {
        "name": "mspaint.exe"
    }
}
```
Hope this helps!"""
        decision = clean_and_normalize_decision(md)
        assert decision["decision_type"] == "tool_call"
        assert decision["type"] == "tool_call"
        assert decision["tool_name"] == "launch_app"
        assert decision["arguments"] == {"name": "mspaint.exe"}

    def test_canonical_tool_call_parsed(self):
        raw = '{"type": "tool_call", "tool_name": "focus_window", "arguments": {"title": "Google Chrome"}}'
        decision = clean_and_normalize_decision(raw)
        assert decision["decision_type"] == "tool_call"
        assert decision["type"] == "tool_call"
        assert decision["tool_name"] == "focus_window"
        assert decision["arguments"] == {"title": "Google Chrome"}

    def test_legacy_normalization_tool_as_top_level_type(self):
        """The critical bug: model returned focus_window directly as type."""
        legacy = '{"type": "focus_window", "arguments": {"title": "Google Chrome"}}'
        decision = clean_and_normalize_decision(legacy)
        assert decision["decision_type"] == "tool_call"
        assert decision["type"] == "tool_call"
        assert decision["tool_name"] == "focus_window"
        assert decision["arguments"] == {"title": "Google Chrome"}

    @pytest.mark.parametrize("tool_name", [
        "launch_app",
        "focus_window",
        "keyboard_type",
        "keyboard_press",
        "keyboard_hotkey",
        "mouse_click",
        "mouse_drag"
    ])
    def test_legacy_normalization_all_registered_tools(self, tool_name):
        raw = json.dumps({"type": tool_name, "arguments": {"test_param": 123}})
        decision = clean_and_normalize_decision(raw)
        assert decision["decision_type"] == "tool_call"
        assert decision["tool_name"] == tool_name
        assert decision["arguments"] == {"test_param": 123}

    def test_normalization_key_variations(self):
        # 'tool' instead of 'tool_name'
        raw1 = '{"type": "tool_call", "tool": "keyboard_type", "args": {"text": "hello"}}'
        d1 = clean_and_normalize_decision(raw1)
        assert d1["tool_name"] == "keyboard_type"
        assert d1["arguments"] == {"text": "hello"}

        # 'action' and 'parameters'
        raw2 = '{"decision_type": "tool_call", "action": "mouse_click", "parameters": {"x": 100, "y": 200}}'
        d2 = clean_and_normalize_decision(raw2)
        assert d2["tool_name"] == "mouse_click"
        assert d2["arguments"] == {"x": 100, "y": 200}

    def test_unknown_decision_type_not_silently_converted_to_tool_call(self):
        raw = '{"type": "random_invalid_action", "arguments": {}}'
        decision = clean_and_normalize_decision(raw)
        # Should preserve the unknown type so validator catches it
        assert decision["decision_type"] == "random_invalid_action"


class TestDecisionValidation:
    """Tests strict validation after normalization."""

    def test_valid_tool_call(self):
        decision = {
            "decision_type": "tool_call",
            "tool_name": "launch_app",
            "arguments": {"name": "mspaint.exe"}
        }
        is_valid, err = validate_model_decision(decision)
        assert is_valid is True
        assert err is None

    def test_focus_window_directly_passed_as_decision_type_auto_normalized(self):
        """Root issue verification: Passing focus_window as type must auto-normalize and pass validation."""
        decision = {
            "type": "focus_window",
            "arguments": {"title": "Paint"}
        }
        allowed = {"focus_window", "launch_app"}
        is_valid, err = validate_model_decision(decision, allowed_tools=allowed)
        assert is_valid is True
        assert err is None
        assert decision["decision_type"] == "tool_call"
        assert decision["tool_name"] == "focus_window"
        assert decision["arguments"] == {"title": "Paint"}

    def test_unknown_tool_name_rejected_with_clear_error(self):
        decision = {
            "decision_type": "tool_call",
            "tool_name": "non_existent_fake_tool",
            "arguments": {}
        }
        allowed = {"launch_app", "focus_window"}
        is_valid, err = validate_model_decision(decision, allowed_tools=allowed)
        assert is_valid is False
        assert "Unknown tool: non_existent_fake_tool" in err

    def test_unknown_decision_type_rejected(self):
        decision = {
            "decision_type": "random_invalid_action",
            "arguments": {}
        }
        is_valid, err = validate_model_decision(decision)
        assert is_valid is False
        assert "Invalid decision type: 'random_invalid_action'" in err

    def test_missing_arguments_rejected(self):
        decision = {
            "decision_type": "tool_call",
            "tool_name": "focus_window"
        }
        is_valid, err = validate_model_decision(decision)
        assert is_valid is False
        assert "Missing 'arguments'" in err

    def test_valid_ask_user_decision(self):
        decision = {
            "decision_type": "ask_user",
            "question": "Which color would you like?"
        }
        is_valid, err = validate_model_decision(decision)
        assert is_valid is True

    def test_valid_wait_decision(self):
        decision = {
            "decision_type": "wait",
            "duration_seconds": 3.5
        }
        is_valid, err = validate_model_decision(decision)
        assert is_valid is True

    def test_valid_final_decision(self):
        decision = {
            "decision_type": "final",
            "message": "Portrait of Mahatma Gandhi completed in Paint!"
        }
        is_valid, err = validate_model_decision(decision)
        assert is_valid is True


class TestLaymanProgressFormatter:
    """Tests that technical actions are translated into friendly layman language."""

    def test_launch_app_layman(self):
        icon, msg = format_layman_action("launch_app", {"name": "mspaint.exe"})
        assert icon == "🚀"
        assert "Opening Microsoft Paint on your computer..." in msg

    def test_focus_window_layman(self):
        icon, msg = format_layman_action("focus_window", {"title": "Google Chrome"})
        assert icon == "🪟"
        assert "Bringing 'Google Chrome' to the front..." in msg

    def test_keyboard_type_layman(self):
        icon, msg = format_layman_action("keyboard_type", {"text": "flights to Pune"})
        assert icon == "⌨️"
        assert "Typing 'flights to Pune'..." in msg

    def test_draw_shape_layman(self):
        icon, msg = format_layman_action("draw_shape", {"shape_type": "circle"})
        assert icon == "🎨"
        assert "Drawing a circle on the canvas..." in msg

    def test_mouse_drag_layman(self):
        icon, msg = format_layman_action("mouse_drag", {"start_x": 100, "start_y": 100, "end_x": 200, "end_y": 200})
        assert icon == "✏️"
        assert "Drawing strokes on the canvas..." in msg

    def test_ask_user_decision_layman(self):
        icon, msg = format_layman_decision({"decision_type": "ask_user", "question": "Which date should I search?"})
        assert icon == "❓"
        assert msg == "Which date should I search?"


class TestEndToEndPipelineReproduction:
    """Reproduces the exact Mahatma Gandhi Paint task through the full normalization and validation pipeline."""

    def test_portrait_task_reproduction_with_tool_call(self):
        # 1. Step 1: Model launches paint
        raw_step1 = '{"type": "tool_call", "tool_name": "launch_app", "arguments": {"name": "mspaint.exe"}}'
        d1 = clean_and_normalize_decision(raw_step1)
        valid1, err1 = validate_model_decision(d1)
        assert valid1 is True
        icon1, msg1 = format_layman_decision(d1)
        assert "Microsoft Paint" in msg1

        # 2. Step 2: Model focuses window (legacy format simulation)
        raw_step2 = '{"type": "focus_window", "arguments": {"title": "Paint"}}'
        d2 = clean_and_normalize_decision(raw_step2)
        valid2, err2 = validate_model_decision(d2)
        assert valid2 is True
        assert d2["decision_type"] == "tool_call"
        assert d2["tool_name"] == "focus_window"
        icon2, msg2 = format_layman_decision(d2)
        assert "Paint" in msg2

        # 3. Step 3: Drawing shapes
        raw_step3 = '{"type": "tool_call", "tool_name": "draw_shape", "arguments": {"shape_type": "circle", "x": 500, "y": 400, "size": 120}}'
        d3 = clean_and_normalize_decision(raw_step3)
        valid3, err3 = validate_model_decision(d3)
        assert valid3 is True
        icon3, msg3 = format_layman_decision(d3)
        assert "circle" in msg3
