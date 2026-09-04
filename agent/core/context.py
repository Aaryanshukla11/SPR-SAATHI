from typing import List, Dict, Any, Tuple, Optional
import json
import re
from agent.tools import get_all_tools
from agent.core import win32_utils

def build_system_instruction() -> str:
    """
    Returns the comprehensive, strict system prompt defining the autonomous Windows agent role,
    the multimodal visual reasoning protocol, and the canonical ModelDecision schema.
    """
    return (
        "You are SPR SAATHI (ORBIT), an autonomous Windows computer use agent controlling a real Windows computer.\n"
        "Use the current visual observation (screenshot and window state) to understand the actual visual state of the computer.\n"
        "Do not assume an action succeeded merely because the execution system returned success.\n"
        "After important actions, inspect the latest observation and determine whether the intended result actually occurred.\n"
        "If the current screen does not match the expected state, choose another action, wait, or replan.\n\n"
        "Respond ONLY with a valid JSON ModelDecision object. Do NOT include markdown blocks, conversational prose, or thinking outside JSON.\n\n"
        "=== STRICT DECISION PROTOCOL HIERARCHY ===\n"
        "The top-level decision type MUST be one of:\n"
        "  - 'tool_call': Execute a registered computer tool.\n"
        "  - 'ask_user': Request human clarification when instructions are ambiguous.\n"
        "  - 'wait': Wait for UI elements or web pages to settle.\n"
        "  - 'replan': Re-decompose plan if current approach fails.\n"
        "  - 'final': Conclude task when verified complete on live screen.\n\n"
        "CRITICAL: Tool names (such as 'launch_app', 'focus_window', 'keyboard_type', 'mouse_click') are NOT top-level decision types.\n"
        "NEVER return {\"type\": \"focus_window\"} or {\"action\": \"launch_app\"}.\n"
        "Every tool execution MUST be wrapped inside a 'tool_call' decision:\n"
        "  {\"decision_type\": \"tool_call\", \"tool_name\": \"<registered_tool_name>\", \"arguments\": {<tool_args>}}\n\n"
        "=== CANONICAL EXAMPLES ===\n"
        "1. Launching an application:\n"
        "   {\"decision_type\": \"tool_call\", \"tool_name\": \"launch_app\", \"arguments\": {\"name\": \"mspaint.exe\"}}\n\n"
        "2. Bringing a window to the front:\n"
        "   {\"decision_type\": \"tool_call\", \"tool_name\": \"focus_window\", \"arguments\": {\"title\": \"Google Chrome\"}}\n\n"
        "3. Typing text into active window:\n"
        "   {\"decision_type\": \"tool_call\", \"tool_name\": \"keyboard_type\", \"arguments\": {\"text\": \"flights to Pune\"}}\n\n"
        "4. Pressing a key:\n"
        "   {\"decision_type\": \"tool_call\", \"tool_name\": \"keyboard_press\", \"arguments\": {\"key\": \"enter\"}}\n\n"
        "5. Pressing a hotkey shortcut:\n"
        "   {\"decision_type\": \"tool_call\", \"tool_name\": \"keyboard_hotkey\", \"arguments\": {\"keys\": [\"ctrl\", \"s\"]}}\n\n"
        "6. Clicking on coordinates:\n"
        "   {\"decision_type\": \"tool_call\", \"tool_name\": \"mouse_click\", \"arguments\": {\"x\": 450, \"y\": 300, \"button\": \"left\"}}\n\n"
        "7. Dragging or sketching on canvas:\n"
        "   {\"decision_type\": \"tool_call\", \"tool_name\": \"mouse_drag\", \"arguments\": {\"start_x\": 300, \"start_y\": 300, \"end_x\": 500, \"end_y\": 500}}\n\n"
        "8. Drawing verified shapes in Paint:\n"
        "   {\"decision_type\": \"tool_call\", \"tool_name\": \"draw_shape\", \"arguments\": {\"shape_type\": \"circle\", \"x\": 400, \"y\": 400, \"size\": 150}}\n\n"
        "9. Asking clarification if instructions are ambiguous or missing:\n"
        "   {\"decision_type\": \"ask_user\", \"question\": \"Could you please specify which date or website you prefer for the ticket search?\"}\n\n"
        "10. Waiting for screen to load:\n"
        "   {\"decision_type\": \"wait\", \"duration_seconds\": 3.0}\n\n"
        "11. Completing task when visually verified:\n"
        "   {\"decision_type\": \"final\", \"message\": \"I have opened Paint and completed drawing the portrait for you!\"}\n\n"
        "=== OPERATIONAL RULES ===\n"
        "1. If the user's task is missing crucial details, use 'ask_user' rather than guessing.\n"
        "2. If the target application is not open, use 'launch_app' to open it. If open but in background, use 'focus_window'.\n"
        "3. Once the application is active and focused, interact using keyboard_type, mouse_click, or drawing tools.\n"
        "4. Visually inspect the screen after each action to confirm progress before deciding the next step.\n"
        "5. Once the requested user goal is visually complete and verified on the live screen, output 'final' decision immediately.\n"
    )

def build_tools_catalog() -> str:
    """
    Returns a concise signature catalog of all registered tools preserving parameter names,
    types, required flags, and concise descriptions.
    """
    tools = get_all_tools()
    lines = []
    for name, tool in tools.items():
        props = tool.parameters.get("properties", {})
        req = tool.parameters.get("required", [])
        param_list = []
        for p_name, p_info in props.items():
            p_type = p_info.get("type", "string")
            is_req = p_name in req
            p_str = f"{p_name}: {p_type}" if is_req else f"{p_name}?: {p_type}"
            param_list.append(p_str)
        sig = f"{tool.name}({', '.join(param_list)})"
        lines.append(f"- {sig}: {tool.description}")
    return "\n".join(lines)

def build_observation_summary(observation: Dict[str, Any]) -> str:
    """
    Builds a concise structured observation representation focusing on visual state,
    active window, screen size, cursor position, and visible application windows.
    """
    lines = []
    
    # Visual Screenshot State Indicator
    image_available = observation.get("image_available", False)
    if image_available:
        lines.append("Visual Observation: Available (Latest screen capture attached to multimodal vision context)")
    else:
        err = observation.get("observation_error") or "No screenshot"
        lines.append(f"Visual Observation: Textual window state only ({err})")

    # Active window with bounds and usable content/canvas area
    active = observation.get("active_window")
    if active:
        title = active.get("title", "Unknown")
        if isinstance(title, str):
            title = title.encode("ascii", "ignore").decode("ascii").strip()
        proc = active.get("process", "unknown")
        b = active.get("bounds", {})
        if b and b.get("width", 0) > 0:
            content_info = win32_utils.get_window_content_bounds(active)
            lines.append(f"Active Window: \"{title}\" ({proc}) | Window Bounds: x={b.get('x',0)}, y={b.get('y',0)}, w={b.get('width',0)}, h={b.get('height',0)}")
            lines.append(f"Usable Content/Canvas Area: x={content_info['x']}, y={content_info['y']}, w={content_info['width']}, h={content_info['height']} (Top header offset: {content_info['top_offset']}px)")
        else:
            lines.append(f"Active Window: \"{title}\" ({proc})")
    else:
        lines.append("Active Window: None (Desktop)")

    # Cursor & Screen
    cursor = observation.get("cursor", {})
    screen = observation.get("screen", {})
    if cursor and screen:
        lines.append(f"Cursor Position: ({cursor.get('x', 0)}, {cursor.get('y', 0)}) | Screen Resolution: {screen.get('width', 1920)}x{screen.get('height', 1080)}")

    # Visible Windows
    vis = observation.get("visible_windows", [])
    ignore_set = {"program manager", "default ime", "msctfime ui", "qa osd", "raycast", "popuphost", "dwm"}
    named_windows = []
    seen = set()
    for w in vis:
        raw_t = w.get("title", "").strip()
        clean_t = raw_t.encode("ascii", "ignore").decode("ascii").strip()
        p = w.get("process", "").strip()
        if clean_t and clean_t.lower() not in ignore_set and clean_t not in seen:
            seen.add(clean_t)
            named_windows.append(f"\"{clean_t}\" ({p})")
    
    if named_windows:
        lines.append(f"Desktop Windows: {', '.join(named_windows[:15])}")
    else:
        lines.append("Desktop Windows: None")

    # Browser State
    browser = observation.get("browser_state")
    if browser and browser.get("is_browser"):
        lines.append(f"Active Browser: {browser.get('browser_name')} | Tab: \"{browser.get('tab_title')}\"")

    # Top Child Controls in Active Window
    hierarchy = observation.get("window_hierarchy", [])
    if hierarchy:
        named_ctrls = []
        for c in hierarchy[:10]:
            c_text = (c.get("text") or "").strip()
            c_class = c.get("class_name", "")
            if c_text:
                named_ctrls.append(f"{c_class}(\"{c_text[:20]}\")")
            elif c_class:
                named_ctrls.append(f"{c_class}")
        if named_ctrls:
            lines.append(f"Window UI Controls: {', '.join(named_ctrls)}")
    
    return "\n".join(lines)

def build_history_summary(recent_history: List[Dict[str, Any]], max_items: int = 5) -> str:
    """
    Builds a concise representation of recently executed actions, their semantic results,
    and resulting visual transitions.
    """
    history_slice = recent_history[-max_items:]
    if not history_slice:
        return "None"
    
    parts = []
    for idx, act in enumerate(history_slice):
        if "action" in act:
            t_name = act.get("action", "unknown")
            args_str = json.dumps(act.get("parameters", {}))
            status = act.get("status", "unknown")
            success = (status == "completed")
            out = str(act.get("output", "") or "").strip()
            err = str(act.get("error", "") or "").strip()
            obs_after = act.get("observation_after", {})
        else:
            tool_call = act.get("tool_call", {})
            tool_res = act.get("tool_result", {})
            t_name = tool_call.get("tool_name", "unknown")
            args_str = json.dumps(tool_call.get("arguments", {}))
            success = tool_res.get("success", False)
            out = str(tool_res.get("output", "") or "").strip()
            err = str(tool_res.get("error", "") or "").strip()
            obs_after = {}
        
        res_summary = f"Success" if success else f"Failed: {err}"
        if out and success:
            res_summary += f" ({out[:60]})"
            
        after_win = obs_after.get("active_window", {}) if isinstance(obs_after, dict) else None
        if after_win and after_win.get("title"):
            res_summary += f" -> [Window: '{after_win.get('title')[:30]}']"

        parts.append(f"[{idx+1}] {t_name}({args_str}) -> {res_summary}")
        
    return "\n".join(parts)

def build_goal_and_plan_summary(goal: str, plan: List[Dict[str, Any]]) -> str:
    """
    Builds a concise plan checklist representation.
    """
    plan_lines = []
    for idx, item in enumerate(plan):
        desc = item.get("description", item.get("step", str(item)))
        status = item.get("status", "pending")
        mark = "[x]" if status == "completed" else "[ ]"
        plan_lines.append(f"{mark} Step {idx+1}: {desc}")
    
    plan_str = "\n".join(plan_lines) if plan_lines else "No checklist"
    return f"Goal: {goal}\nPlan:\n{plan_str}"

def sanitize_sensitive_data(text: str) -> str:
    """
    Phase 9 Privacy Boundary: Redacts secret tokens, API keys, passwords,
    and private bearer tokens before sending prompt context to AI models.
    """
    if not isinstance(text, str) or not text:
        return ""

    # Common API key and bearer token patterns
    sanitized = re.sub(r"sk-[a-zA-Z0-9_\-]{20,}", "[REDACTED_API_KEY]", text)
    sanitized = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED_GOOGLE_KEY]", sanitized)
    sanitized = re.sub(r"ghp_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_TOKEN]", sanitized)
    sanitized = re.sub(r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]{25,}", r"\1[REDACTED_TOKEN]", sanitized)
    sanitized = re.sub(r"(?i)(password|secret|api_key|token)\s*([:=])\s*['\"]?[^\s'\",]{8,}['\"]?", r"\1\2 [REDACTED]", sanitized)
    return sanitized


class ContextBuilder:
    """
    Phase 9: Context Builder Engine.
    
    Synthesizes and selects relevant context across 9 sources:
    1. User request & overarching goal
    2. Structured plan checklist
    3. Multimodal visual & textual desktop observation
    4. Relevant memories (retrieved from MemoryManager)
    5. Relevant workspace files (retrieved from WorkspaceManager)
    6. Compact action history with large-history sliding window
    7. Tool catalog
    8. Active browser and window controls
    9. Privacy boundaries sanitization
    """

    def __init__(self):
        pass

    def build_context(
        self,
        goal: str,
        plan: List[Dict[str, Any]],
        observation: Dict[str, Any],
        recent_history: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        include_memories: bool = True,
        include_workspace_files: bool = True
    ) -> Tuple[str, str]:
        # 1. System Prompt
        sys_prompt = build_system_instruction()

        # 2. Tool Catalog
        tools_catalog = build_tools_catalog()

        # 3. Visual & Desktop Observation
        obs_summary = build_observation_summary(observation)

        # 4. Action History with sliding window for large histories
        hist_summary = build_history_summary(recent_history, max_items=6)

        # 5. Goal & Plan Checklist
        goal_plan = build_goal_and_plan_summary(goal, plan)

        sections = [
            f"=== GOAL & PLAN ===\n{goal_plan}",
            f"=== CURRENT OBSERVATION ===\n{obs_summary}",
            f"=== RECENT ACTION HISTORY ===\n{hist_summary}"
        ]

        # 6. Relevant Memories
        if include_memories:
            try:
                from agent.core.memory import MEMORY_MANAGER
                mem_matches = MEMORY_MANAGER.retrieve_relevant(goal, limit=3)
                if mem_matches:
                    mem_lines = [f"- [{m.key}]: {m.content}" for m, _ in mem_matches]
                    sections.append(f"=== RELEVANT USER MEMORIES ===\n" + "\n".join(mem_lines))
            except Exception:
                pass

        # 7. Relevant Workspace Files
        if include_workspace_files:
            try:
                from agent.core.workspace import WORKSPACE_MANAGER
                file_matches = WORKSPACE_MANAGER.search_files(goal, max_results=3)
                if file_matches:
                    file_lines = [f"- {meta.filename} ({meta.file_type.value}, {meta.size_bytes}B)" for meta, _ in file_matches]
                    sections.append(f"=== RELEVANT WORKSPACE FILES ===\n" + "\n".join(file_lines))
            except Exception:
                pass

        # 8. Conversation History (if present)
        if conversation_history:
            conv_lines = []
            for turn in conversation_history[-4:]:
                r = turn.get("role", "user")
                m = turn.get("message", "")
                conv_lines.append(f"{r.capitalize()}: {m}")
            if conv_lines:
                sections.append("=== RECENT CONVERSATION ===\n" + "\n".join(conv_lines))

        # 9. Tools Catalog
        sections.append(f"=== TOOLS CATALOG ===\n{tools_catalog}")
        sections.append("Inspect the current observation/screen and decide the next action to execute (use 'tool_call' with 'tool_name' and 'arguments', or 'final' if completed). Return JSON only.")

        user_content = "\n\n".join(sections)

        # Enforce Phase 9 Privacy Boundaries: strip any accidental credentials
        clean_user_content = sanitize_sensitive_data(user_content)

        return sys_prompt, clean_user_content


# Global singleton instance
CONTEXT_BUILDER = ContextBuilder()


def build_compact_context(
    goal: str,
    plan: List[Dict[str, Any]],
    observation: Dict[str, Any],
    recent_history: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """
    Constructs the optimized system prompt and user prompt payload via ContextBuilder.
    """
    return CONTEXT_BUILDER.build_context(
        goal=goal,
        plan=plan,
        observation=observation,
        recent_history=recent_history
    )

