from typing import List, Dict, Any, Tuple, Optional
import json
from agent.tools import get_all_tools
from agent.core import win32_utils

def build_system_instruction() -> str:
    """
    Returns the comprehensive, strict system prompt defining the autonomous Windows agent role,
    the multimodal visual reasoning protocol, and the canonical ModelDecision schema.
    """
    return (
        "You are SPR SAATHI, an autonomous Windows computer use agent controlling a real Windows computer.\n"
        "Use the current visual observation (screenshot and window state) to understand the actual visual state of the computer.\n"
        "Do not assume an action succeeded merely because the execution system returned success.\n"
        "After important actions, inspect the latest observation and determine whether the intended result actually occurred.\n"
        "If the current screen does not match the expected state, choose another action, wait, or replan.\n\n"
        "Respond ONLY with a valid JSON ModelDecision object. Do NOT include markdown blocks, conversational prose, or thinking outside JSON.\n\n"
        "=== SCHEMA ===\n"
        "- tool_call: {\"decision_type\": \"tool_call\", \"tool_name\": \"<catalog_tool_name>\", \"arguments\": {<tool_args>}}\n"
        "- final: {\"decision_type\": \"final\", \"message\": \"<task_completion_summary>\"}\n"
        "- replan: {\"decision_type\": \"replan\", \"reason\": \"<why_plan_changed>\"} (use if goal requires alternative approach)\n"
        "- ask_user: {\"decision_type\": \"ask_user\", \"question\": \"<clarification_query>\"}\n"
        "- wait: {\"decision_type\": \"wait\", \"duration_seconds\": <number>}\n\n"
        "=== OPERATIONAL RULES ===\n"
        "1. Execute actions using 'tool_call'. Both 'tool_name' and 'arguments' are required.\n"
        "2. If the target application is not open, use 'launch_app' to open it. If open but in the background, use 'focus_window'.\n"
        "3. When the window is active and focused, interact using keyboard_type, mouse_click, or mouse_drag.\n"
        "4. For geometric/canvas drawing tasks, use dedicated drawing tools:\n"
        "   - 'draw_shape': Draws verified geometric figures and shapes (arguments: shape_type, x, y, size, depth)\n"
        "   - 'draw_rectangle': Draws a rectangle (arguments: x, y, width, height)\n"
        "   - 'draw_line' / 'draw_polyline' / 'mouse_drag': For continuous verified strokes in canvas coordinate space.\n"
        "5. Visually inspect the screen after each action to confirm progress before deciding the next step.\n"
        "6. Once the requested user goal is visually complete and verified on the live screen, output 'final' decision immediately.\n"
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

def build_compact_context(
    goal: str,
    plan: List[Dict[str, Any]],
    observation: Dict[str, Any],
    recent_history: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """
    Constructs the optimized system prompt and user prompt payload.
    """
    sys_prompt = build_system_instruction()
    tools_catalog = build_tools_catalog()
    obs_summary = build_observation_summary(observation)
    hist_summary = build_history_summary(recent_history)
    goal_plan = build_goal_and_plan_summary(goal, plan)

    user_content = (
        f"=== GOAL & PLAN ===\n{goal_plan}\n\n"
        f"=== CURRENT OBSERVATION ===\n{obs_summary}\n\n"
        f"=== RECENT ACTION HISTORY ===\n{hist_summary}\n\n"
        f"=== TOOLS CATALOG ===\n{tools_catalog}\n\n"
        "Inspect the current observation/screen and decide the next action to execute (use 'tool_call' with 'tool_name' and 'arguments', or 'final' if completed). Return JSON only."
    )
    return sys_prompt, user_content
