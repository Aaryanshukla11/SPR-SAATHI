from typing import Dict, Any, Tuple, Optional

def get_app_display_name(raw_name: str) -> str:
    """Converts executable or process names into user-friendly names."""
    if not raw_name:
        return "Application"
    low = raw_name.lower().strip()
    if "mspaint" in low or "paint" in low:
        return "Microsoft Paint"
    if "chrome" in low:
        return "Google Chrome"
    if "notepad" in low:
        return "Notepad"
    if "calc" in low:
        return "Calculator"
    if "msedge" in low or "edge" in low:
        return "Microsoft Edge"
    if "code" in low:
        return "Visual Studio Code"
    if "explorer" in low:
        return "File Explorer"
    if "cmd" in low:
        return "Command Prompt"
    if "powershell" in low:
        return "PowerShell"
    
    # Strip extension
    clean = raw_name.replace(".exe", "").replace(".EXE", "")
    return clean.capitalize()


def format_layman_action(tool_name: str, args: Dict[str, Any]) -> Tuple[str, str]:
    """
    Translates technical tool calls and parameters into concise, friendly
    layman descriptions that anyone can understand without technical jargon.
    Returns (icon, message).
    """
    args = args or {}
    t = (tool_name or "").lower().strip()

    if t == "launch_app":
        app_name = get_app_display_name(str(args.get("name") or args.get("app_name") or ""))
        return "🚀", f"Opening {app_name} on your computer..."

    elif t == "focus_window":
        title = str(args.get("title") or args.get("window_name") or "").strip()
        if title:
            return "🪟", f"Bringing '{title}' to the front..."
        return "🪟", "Bringing window to the front..."

    elif t == "list_windows":
        return "🔍", "Checking open windows on your screen..."

    elif t == "take_screenshot":
        return "📸", "Observing the current screen state..."

    elif t == "mouse_click":
        button = str(args.get("button", "left")).lower()
        if button == "right":
            return "🖱️", "Right-clicking to open menu..."
        return "👆", "Clicking on the screen..."

    elif t == "mouse_double_click":
        return "👆", "Double-clicking item..."

    elif t in ["mouse_drag", "draw_line"]:
        return "✏️", "Drawing strokes on the canvas..."

    elif t == "draw_shape":
        shape = str(args.get("shape_type", "shape")).lower()
        return "🎨", f"Drawing a {shape} on the canvas..."

    elif t == "draw_rectangle":
        return "📐", "Drawing a rectangle on the canvas..."

    elif t == "draw_polyline":
        return "✏️", "Sketching continuous lines..."

    elif t == "mouse_move":
        return "🖱️", "Moving cursor to target position..."

    elif t == "mouse_scroll":
        clicks = args.get("clicks", 0)
        direction = "down" if (isinstance(clicks, (int, float)) and clicks < 0) else "up"
        return "📜", f"Scrolling {direction} to see more content..."

    elif t == "keyboard_type":
        text = str(args.get("text", "")).strip()
        if len(text) > 30:
            text_preview = text[:27] + "..."
        else:
            text_preview = text
        if text_preview:
            return "⌨️", f"Typing '{text_preview}'..."
        return "⌨️", "Typing into the active window..."

    elif t == "keyboard_press":
        key = str(args.get("key", "")).strip()
        if key.lower() == "enter":
            return "↵", "Pressing Enter to submit..."
        elif key.lower() == "tab":
            return "⇥", "Pressing Tab to navigate..."
        elif key.lower() in ["esc", "escape"]:
            return "⎋", "Pressing Escape..."
        return "⌨️", f"Pressing key: {key}..."

    elif t == "keyboard_hotkey":
        keys = args.get("keys", [])
        if isinstance(keys, list):
            hotkey_str = "+".join(str(k).upper() for k in keys)
            return "⌨️", f"Pressing keyboard shortcut {hotkey_str}..."
        return "⌨️", "Pressing keyboard shortcut..."

    elif t == "open_browser_url":
        url = str(args.get("url", "")).strip()
        return "🌐", f"Opening web page {url}..."

    elif t == "web_search":
        query = str(args.get("query", "")).strip()
        return "🔎", f"Searching online for '{query}'..."

    elif t == "create_file":
        path = str(args.get("path") or args.get("filepath") or "").strip()
        fname = path.split("\\")[-1].split("/")[-1] if path else "file"
        return "📄", f"Creating file '{fname}'..."

    elif t == "read_file":
        path = str(args.get("path") or args.get("filepath") or "").strip()
        fname = path.split("\\")[-1].split("/")[-1] if path else "file"
        return "📖", f"Reading contents of '{fname}'..."

    elif t in ["cmd", "powershell"]:
        cmd_str = str(args.get("command", "")).strip()
        if len(cmd_str) > 25:
            cmd_preview = cmd_str[:22] + "..."
        else:
            cmd_preview = cmd_str
        return "⚡", f"Running command: {cmd_preview}..."

    return "⚙️", f"Performing action: {tool_name}..."


def format_layman_decision(decision: Dict[str, Any]) -> Tuple[str, str]:
    """
    Translates top-level agent decisions into user-friendly layman language.
    Returns (icon, message).
    """
    decision = decision or {}
    dtype = (decision.get("decision_type") or decision.get("type") or "").lower()

    if dtype == "tool_call":
        tool_name = decision.get("tool_name", "")
        arguments = decision.get("arguments", {})
        return format_layman_action(tool_name, arguments)

    elif dtype == "wait":
        dur = decision.get("duration_seconds", 2)
        try:
            val = round(float(dur), 1)
        except Exception:
            val = 2
        return "⏳", f"Waiting {val}s for the screen to settle..."

    elif dtype == "replan":
        reason = str(decision.get("reason", "")).strip()
        if reason:
            return "🔄", f"Adjusting approach: {reason}"
        return "🔄", "Adjusting plan to complete your task..."

    elif dtype == "ask_user":
        question = str(decision.get("question", "")).strip()
        return "❓", question or "Needs clarification to proceed."

    elif dtype == "final":
        msg = str(decision.get("message", "")).strip()
        return "✅", msg or "Task completed successfully!"

    return "🤖", "ORBIT is thinking..."
