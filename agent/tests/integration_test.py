import asyncio
import sys
from agent.core.state import StateTracker
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.core.executor import ToolExecutor
from agent.core.planner import RuleBasedPlanner
from agent.core.loop import AgentLoop
from agent.tools import get_all_tools
from agent.core import win32_utils
from agent.models.api import ApiModelProvider

async def run_integration_test():
    print("====================================================")
    print("STARTING SPR SAATHI WINDOWS INTEGRATION TEST")
    print("====================================================")
    
    if sys.platform != "win32":
        print("Skipping integration test: not running on Windows OS.")
        return

    # 1. Initialize backend components
    tracker = StateTracker()
    mock_provider = ApiModelProvider(model_name="Gemini 3.5 Flash")
    
    async def mock_decide_action(goal, plan, observation, recent_history, **kwargs):
        launched = any(a.get("action") == "launch_app" for a in recent_history if a.get("status") == "completed")
        focused = any(a.get("action") == "focus_window" for a in recent_history if a.get("status") == "completed")
        typed = any(a.get("action") == "keyboard_type" and "hello" in str(a.get("parameters", {}).get("text")).lower() for a in recent_history if a.get("status") == "completed")
        if not launched:
            return {"decision_type": "tool_call", "tool_name": "launch_app", "arguments": {"app_name": "notepad.exe"}}
        if not focused:
            return {"decision_type": "tool_call", "tool_name": "focus_window", "arguments": {"process_name": "notepad.exe", "title_substring": "Notepad"}}
        if not typed:
            return {"decision_type": "tool_call", "tool_name": "keyboard_type", "arguments": {"text": "Hello SPR Saathi."}}
        return {"decision_type": "final", "message": "Task completed successfully"}
        
    mock_provider.decide_action = mock_decide_action
    planner = RuleBasedPlanner(mock_provider)
    
    # Allow all permissions for automation test
    import os, tempfile
    fd, config_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    pm = PolicyManager(config_path=config_path)
    pm.update_policy("mouse", "allow")
    pm.update_policy("keyboard", "allow")
    pm.update_policy("applications", "allow")
    pm.update_app_policy("notepad.exe", "allow")
    
    broker = PermissionBroker(pm)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker)
    
    # Simple takeover manager
    from agent.control.takeover import TakeoverManager
    takeover_manager = TakeoverManager()
    
    # Print status changes to console
    async def console_broadcast(event):
        msg = event.get("message", "")
        event_type = event.get("event_type", "").upper()
        print(f"[{event_type}] {msg}")
        if event_type == "OBSERVE" and "active_window" in event.get("payload", {}):
            win = event["payload"]["active_window"]
            if win:
                print(f"    -> Focused: '{win['title']}' [Process: {win['process']}]")

    loop = AgentLoop(
        state_tracker=tracker,
        planner=planner,
        executor=executor,
        takeover_manager=takeover_manager,
        broadcast_callback=console_broadcast
    )
    
    # 2. Run Task: Open Notepad and type Hello SPR Saathi.
    task_desc = "Open Notepad and type Hello SPR Saathi."
    loop.start_task(task_desc)
    
    # Monitor loop status for up to 10 seconds
    max_duration = 10.0
    elapsed = 0.0
    poll_interval = 0.5
    
    while tracker.status not in ["completed", "error", "stopped"] and elapsed < max_duration:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        
    print("----------------------------------------------------")
    print(f"Task completed loop check. Status: {tracker.status}")
    print("----------------------------------------------------")
    
    # Assert successful loop execution
    assert tracker.status == "completed", f"Task failed with error: {tracker.error_message}"
    
    # 3. Rest so user can see typed text
    print("Resting for 3 seconds to verify text visually...")
    await asyncio.sleep(3.0)
    
    # 4. Clean up: Locate the Notepad window and send close request
    print("Cleaning up: Closing Notepad...")
    windows = win32_utils.list_desktop_windows()
    notepad_hwnd = None
    for w in windows:
        if "notepad.exe" in w["process"].lower():
            notepad_hwnd = w["hwnd"]
            break
            
    if notepad_hwnd:
        # Focus it
        win32_utils.focus_window(notepad_hwnd)
        await asyncio.sleep(0.5)
        # Send WM_CLOSE
        win32_utils.close_window(notepad_hwnd)
        await asyncio.sleep(0.5)
        
        # Tap 'N' or 'n' key to discard save dialog if notepad asks
        # (Since we modified the file, notepad will ask: "Do you want to save changes?")
        # On Windows 10/11, standard hotkey to discard save is "Don't Save" which is mapped to 'n' or 'tab + enter'
        print("Tapping 'N' to discard Notepad save prompt...")
        # Press N
        win32_utils.press_key("N")
        await asyncio.sleep(0.5)
        print("Notepad closed cleanly.")
    else:
        print("Could not find Notepad window to close.")
        
    if os.path.exists(config_path):
        try:
            os.remove(config_path)
        except Exception:
            pass
            
    print("====================================================")
    print("INTEGRATION TEST SUCCESSFUL!")
    print("====================================================")

import pytest

@pytest.mark.asyncio
async def test_integration_notepad_flow():
    await run_integration_test()

if __name__ == "__main__":
    asyncio.run(run_integration_test())
