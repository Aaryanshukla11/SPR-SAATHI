from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# Typed Pipeline Exceptions
class ModelPipelineError(Exception):
    """Base exception for all model pipeline failures."""
    pass

class ModelNetworkError(ModelPipelineError):
    """Network connection failure or timeout reaching model service."""
    pass

class ModelServiceUnavailableError(ModelPipelineError):
    """Local model service (e.g. Ollama) is not running or unreachable."""
    pass

class ModelHttpError(ModelPipelineError):
    """HTTP status error from model service (4xx, 5xx)."""
    def __init__(self, status_code: int, message: str, endpoint: str = ""):
        self.status_code = status_code
        self.endpoint = endpoint
        super().__init__(f"HTTP {status_code} from {endpoint}: {message}")

class ModelEmptyResponseError(ModelPipelineError):
    """API service returned an empty or whitespace-only response body."""
    pass

class ModelApiJsonError(ModelPipelineError):
    """API response body is not valid JSON (Layer 1 failure)."""
    pass

class ModelInvalidContentError(ModelPipelineError):
    """API JSON is valid, but model content/candidates is missing or blocked."""
    pass

class ModelDecisionParseError(ModelPipelineError):
    """Model generated text could not be parsed into a structured decision (Layer 2 failure)."""
    pass

class ModelDecisionValidationError(ModelPipelineError):
    """Model decision JSON failed schema or tool registry validation."""
    pass


def safe_parse_api_json(response_text: str, endpoint: str = "", status_code: int = 200) -> Dict[str, Any]:
    """
    Layer 1 Validation: Safely parses HTTP response text as an API JSON payload.
    Prevents unhandled crashes on empty bodies, HTML error pages, or non-JSON proxies.
    """
    import json
    if not response_text or not response_text.strip():
        raise ModelEmptyResponseError(f"Empty HTTP response body received from {endpoint or 'API service'} (HTTP {status_code}).")
    
    text = response_text.strip()
    try:
        data = json.loads(text)
        if not isinstance(data, (dict, list)):
            raise ModelApiJsonError(f"API returned non-container JSON from {endpoint or 'API'}: {text[:100]!r}")
        return data if isinstance(data, dict) else {"items": data}
    except json.JSONDecodeError as e:
        preview = text[:120].replace("\n", " ")
        raise ModelApiJsonError(f"Failed to parse API JSON from {endpoint or 'API'} (HTTP {status_code}): {str(e)}. Response preview: {preview!r}")


class ModelResponse(BaseModel):
    text: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Any = None

class ModelDecision(BaseModel):
    decision_type: str = Field(..., description="Must be 'tool_call', 'final', 'replan', 'ask_user', or 'wait'")
    type: Optional[str] = None
    tool_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    question: Optional[str] = None
    duration_seconds: Optional[float] = None
    reason: Optional[str] = None

KNOWN_COMPUTER_TOOLS = {
    "focus_window", "launch_app", "mouse_click", "mouse_move", "mouse_drag", "mouse_scroll", 
    "mouse_down", "mouse_up", "keyboard_type", "keyboard_press", "keyboard_hotkey", 
    "keyboard_key_down", "keyboard_key_up", "draw_shape", "draw_pencil", "draw_sketch", 
    "draw_color_palette", "draw_fill_bucket", "file_read", "file_write", "file_list", 
    "process_list", "window_list", "take_screenshot", "screen_ocr"
}

def validate_model_decision(decision: Dict[str, Any], allowed_tools: Optional[Any] = None) -> tuple[bool, Optional[str]]:
    """
    Validates model output schemas and values against the Typed Decision Protocol.
    Verifies top-level decision types and registered tool existence.
    Auto-normalizes computer actions passed directly as decision types (Root Fix).
    Returns (is_valid, error_message).
    """
    if not isinstance(decision, dict):
        return False, "Decision must be a JSON dictionary."

    # Resolve tool registry for auto-normalization and validation
    if allowed_tools is None:
        try:
            from agent.tools import get_all_tools
            allowed_tools = set(get_all_tools().keys())
        except Exception:
            allowed_tools = None
    elif not isinstance(allowed_tools, set):
        allowed_tools = set(allowed_tools)

    dtype = decision.get("decision_type") or decision.get("type")
    valid_types = {"tool_call", "final", "replan", "ask_user", "wait"}

    # ROOT CAUSE DEFENSE: Auto-normalize computer tool names returned as top-level decision type
    if dtype and dtype not in valid_types:
        is_tool = False
        if allowed_tools is not None and dtype in allowed_tools:
            is_tool = True
        elif dtype in KNOWN_COMPUTER_TOOLS:
            is_tool = True

        if is_tool:
            decision["decision_type"] = "tool_call"
            decision["type"] = "tool_call"
            decision["tool_name"] = dtype
            if "arguments" not in decision:
                decision["arguments"] = decision.get("args") or decision.get("parameters") or {}
            dtype = "tool_call"

    if dtype not in valid_types:
        return False, f"Invalid decision type: '{dtype}'. Must be one of {valid_types}."

    if dtype == "tool_call":
        tool_name = decision.get("tool_name")
        if not tool_name:
            return False, "Missing 'tool_name' in 'tool_call' decision."
        if decision.get("arguments") is None:
            return False, "Missing 'arguments' in 'tool_call' decision."
        if not isinstance(decision.get("arguments"), dict):
            return False, "'arguments' in 'tool_call' decision must be a dictionary."
        
        # Tool registry validation (check tool exists)
        if allowed_tools is not None and tool_name not in allowed_tools:
            return False, f"Unknown tool: {tool_name}"
            
    elif dtype == "final":
        if not decision.get("message"):
            return False, "Missing 'message' in 'final' decision."
            
    elif dtype == "replan":
        if not decision.get("reason"):
            return False, "Missing 'reason' in 'replan' decision."
            
    elif dtype == "ask_user":
        if not decision.get("question"):
            return False, "Missing 'question' in 'ask_user' decision."
            
    elif dtype == "wait":
        duration = decision.get("duration_seconds")
        if duration is None:
            return False, "Missing 'duration_seconds' in 'wait' decision."
        try:
            val = float(duration)
            if val <= 0:
                return False, "'duration_seconds' must be positive."
        except (ValueError, TypeError):
            return False, "'duration_seconds' must be a valid number."

    return True, None

def clean_and_normalize_decision(content: str, allowed_tools: Optional[Any] = None) -> Dict[str, Any]:
    """
    Layer 2 Normalization: Safely parses model output text, strips markdown blocks,
    normalizes legacy tool-as-type formats into canonical tool_call decisions,
    and returns a clean internal dictionary representation.
    """
    import re
    import json
    
    if not content or not str(content).strip():
        raise ModelDecisionParseError("Model returned an empty response. Expected a valid JSON decision object.")

    content = str(content).strip()
    
    # Check if there are markdown code blocks wrapping JSON
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if match:
        extracted = match.group(1).strip()
    else:
        # Check if there is some JSON-like structure inside curly braces
        match = re.search(r"(\{.*\})", content, re.DOTALL)
        if match:
            extracted = match.group(1).strip()
        elif "{" in content:
            preview = content[-120:].replace("\n", " ")
            raise ModelDecisionParseError(f"Model returned truncated or incomplete JSON decision (unclosed brace). Snippet: {preview!r}")
        else:
            preview = content[:120].replace("\n", " ")
            raise ModelDecisionParseError(f"Model returned plain text or unparseable output without a JSON decision object. Output preview: {preview!r}")
            
    try:
        decision = json.loads(extracted)
    except json.JSONDecodeError as e:
        if not extracted.rstrip().endswith("}"):
            raise ModelDecisionParseError(f"Model returned truncated or incomplete JSON decision: {str(e)}. Snippet: {extracted[-80:]!r}")
        preview = extracted[:120].replace("\n", " ")
        raise ModelDecisionParseError(f"Model decision contains malformed JSON: {str(e)}. Snippet: {preview!r}")

    if not isinstance(decision, dict):
        raise ModelDecisionParseError("Decided action must be a JSON object dictionary.")
        
    # Get registered tools for legacy normalization if not provided
    if allowed_tools is None:
        try:
            from agent.tools import get_all_tools
            allowed_tools = set(get_all_tools().keys())
        except Exception:
            allowed_tools = set()
    elif not isinstance(allowed_tools, set):
        allowed_tools = set(allowed_tools)

    normalized: Dict[str, Any] = {}
    valid_types = {"tool_call", "final", "replan", "ask_user", "wait"}
    
    # 1. Raw decision type detection
    raw_type = decision.get("decision_type") or decision.get("type") or decision.get("action_type")
    raw_type_str = str(raw_type).strip().lower() if raw_type else None

    # 2. Tool name detection
    tname = decision.get("tool_name") or decision.get("tool") or decision.get("name") or decision.get("action")
    tname_str = str(tname).strip() if tname else None

    # 3. Arguments detection
    args = decision.get("arguments")
    if args is None:
        args = decision.get("args") or decision.get("parameters") or decision.get("params")
        
    # Normalization Logic
    if raw_type_str in valid_types:
        # Standard canonical decision
        normalized["decision_type"] = raw_type_str
        normalized["type"] = raw_type_str
        if raw_type_str == "tool_call":
            normalized["tool_name"] = tname_str or ""
            normalized["arguments"] = args if isinstance(args, dict) else {}
    elif raw_type_str in allowed_tools or raw_type_str in KNOWN_COMPUTER_TOOLS:
        # Legacy/misaligned model output where tool name was returned as top-level type
        # e.g. {"type": "focus_window", "arguments": {"title": "Google Chrome"}}
        normalized["decision_type"] = "tool_call"
        normalized["type"] = "tool_call"
        normalized["tool_name"] = raw_type_str
        normalized["arguments"] = args if isinstance(args, dict) else {}
    elif raw_type_str:
        # Unknown decision type: preserve as-is so validate_model_decision produces an explicit error
        normalized["decision_type"] = raw_type_str
        normalized["type"] = raw_type_str
        if tname_str:
            normalized["tool_name"] = tname_str
        if args is not None:
            normalized["arguments"] = args
    else:
        # Missing type entirely
        if tname_str and (tname_str in allowed_tools or tname_str in KNOWN_COMPUTER_TOOLS):
            normalized["decision_type"] = "tool_call"
            normalized["type"] = "tool_call"
            normalized["tool_name"] = tname_str
            normalized["arguments"] = args if isinstance(args, dict) else {}

    # Map other standard fields
    msg = decision.get("message") or decision.get("msg") or decision.get("text")
    if msg:
        normalized["message"] = str(msg).strip()
        
    q = decision.get("question") or decision.get("query")
    if q:
        normalized["question"] = str(q).strip()
        
    dur = decision.get("duration_seconds") or decision.get("duration") or decision.get("wait_seconds")
    if dur is not None:
        normalized["duration_seconds"] = dur
        
    reason = decision.get("reason") or decision.get("explanation")
    if reason:
        normalized["reason"] = str(reason).strip()
        
    # Copy remaining attributes
    for k, v in decision.items():
        if k not in normalized:
            normalized[k] = v
            
    normalized["_raw_response"] = content
    return normalized

class BaseModelProvider(ABC):
    def __init__(self, model_name: str, config: Optional[Dict[str, Any]] = None):
        self.model_name = model_name
        self.config = config or {}

    @property
    def capabilities(self) -> Dict[str, Any]:
        """Expose capabilities of the model."""
        return {
            "supports_tool_calling": True,
            "supports_structured_output": True,
            "supports_vision": False,
            "supports_streaming": False,
            "context_window": 128000
        }

    @property
    def supports_vision(self) -> bool:
        """Returns True if this model provider instance supports image/multimodal input."""
        return bool(self.capabilities.get("supports_vision", False))

    @abstractmethod
    async def generate(self, prompt: str, system_instruction: Optional[str] = None, image_base64: Optional[str] = None) -> ModelResponse:
        """Generates text from a prompt."""
        pass

    @abstractmethod
    async def generate_with_tools(self, prompt: str, tools: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> ModelResponse:
        """Generates completing structured tool calls if requested."""
        pass

    @abstractmethod
    async def decide_action(
        self, 
        goal: str, 
        plan: List[Dict[str, Any]], 
        observation: Dict[str, Any], 
        recent_history: List[Dict[str, Any]],
        image_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        """Returns a structured next action decision."""
        pass
