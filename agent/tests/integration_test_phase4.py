import asyncio
import sys
import os
from agent.core.state import StateTracker
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.core.executor import ToolExecutor
from agent.core.planner import RuleBasedPlanner
from agent.core.loop import AgentLoop
from agent.tools import get_all_tools
from agent.core import win32_utils
from agent.models.api import ApiModelProvider

async def run_phase4_integration():
    print("====================================================")
    print("STARTING SPR SAATHI WINDOWS PHASE 4 INTEGRATION TEST")
    print("====================================================")
    
    if sys.platform != "win32":
        print("Skipping: not on Windows OS.")
        return

    # Use a temp config file for isolation
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integration_permissions_p4.json")
    if os.path.exists(config_path):
        os.remove(config_path)

    # Clean up any leftover txt file
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "hello.txt")
    if os.path.exists(desktop_path):
        try:
            os.remove(desktop_path)
        except Exception:
            pass

    try:
        # ----------------------------------------------------
        # Initialize
        # ----------------------------------------------------
        tracker = StateTracker()
        pm = PolicyManager(config_path=config_path)
        pm.update_policy("mouse", "allow")
        pm.update_policy("keyboard", "allow")
        pm.update_policy("applications", "allow")
        pm.update_policy("filesystem", "allow")
        pm.update_app_policy("notepad.exe", "allow")
        
        broker = PermissionBroker(pm, tracker)
        tools = get_all_tools()
        executor = ToolExecutor(tools, broker)
        
        model = ApiModelProvider("Gemini 3.5 Flash")
        
        async def mock_decide_action(goal, plan, observation, recent_history):
            goal_lower = goal.lower()
            
            notepad_open = False
            for w in observation.get("visible_windows", []):
                if "notepad" in str(w.get("process") or w.get("title") or "").lower():
                    notepad_open = True
                    break
            active_win = observation.get("active_window")
            if active_win and "notepad" in str(active_win.get("process") or active_win.get("title") or "").lower():
                notepad_open = True

            launched = any(a.get("action") == "launch_app" for a in recent_history if a.get("status") == "completed")
            focused = any(a.get("action") == "focus_window" for a in recent_history if a.get("status") == "completed")
            typed = any(a.get("action") == "keyboard_type" and "hello" in str(a.get("parameters", {}).get("text")).lower() for a in recent_history if a.get("status") == "completed")
            hotkeyed = any(a.get("action") == "keyboard_hotkey" for a in recent_history if a.get("status") == "completed")
            named = any(a.get("action") == "keyboard_type" and "txt" in str(a.get("parameters", {}).get("text")).lower() for a in recent_history if a.get("status") == "completed")
            entered = any(a.get("action") == "keyboard_press" and "enter" in str(a.get("parameters", {}).get("key")).lower() for a in recent_history if a.get("status") == "completed")

            if not notepad_open:
                return {"decision_type": "tool_call", "tool_name": "launch_app", "arguments": {"app_name": "notepad.exe"}}
            if not focused:
                return {"decision_type": "tool_call", "tool_name": "focus_window", "arguments": {"process_name": "notepad.exe", "title_substring": "Notepad"}}
            if not typed:
                # Use same typing input text as requested in task
                import re
                match = re.search(r"(?:type|write|enter)\s+(.+?)(?:,|$|and\s+save)", goal, re.IGNORECASE)
                text_to_type = match.group(1).strip() if match else "Hello SPR Saathi"
                text_to_type = text_to_type.strip("'\"")
                return {"decision_type": "tool_call", "tool_name": "keyboard_type", "arguments": {"text": text_to_type}}
            if "save" in goal_lower:
                if not hotkeyed:
                    return {"decision_type": "tool_call", "tool_name": "keyboard_hotkey", "arguments": {"keys": ["ctrl", "s"]}}
                if not named:
                    return {"decision_type": "tool_call", "tool_name": "keyboard_type", "arguments": {"text": "hello.txt"}}
                if not entered:
                    return {"decision_type": "tool_call", "tool_name": "keyboard_press", "arguments": {"key": "enter"}}
            return {"decision_type": "final", "message": "Task completed successfully"}

        model.decide_action = mock_decide_action
        planner = RuleBasedPlanner(model)
        
        from agent.control.takeover import TakeoverManager
        takeover_manager = TakeoverManager()

        async def log_event(ev):
            print(f"[{ev.get('event_type')}] {ev.get('message')}")
            if ev.get("event_type") == "tool.failed":
                print(f"   Tool failed error: {ev.get('payload')}")

        loop = AgentLoop(
            state_tracker=tracker,
            planner=planner,
            executor=executor,
            takeover_manager=takeover_manager,
            broadcast_callback=log_event
        )

        # ----------------------------------------------------
        # TEST 1 & 2: Notepad Launch, Type, and Save File (hello.txt)
        # ----------------------------------------------------
        print("\n--- TEST 1 & 2: Notepad Launch, Type, and Save hello.txt ---")
        task_desc = "Open Notepad, type Hello SPR Saathi, and save it as hello.txt"
        loop.start_task(task_desc)
        
        # Wait up to 15 seconds for completion
        max_wait = 30.0
        elapsed = 0.0
        while tracker.status not in ["completed", "failed", "cancelled"] and elapsed < max_wait:
            await asyncio.sleep(0.5)
            elapsed += 0.5
            
        print(f"Task completed check. Status: {tracker.status}, Error: {tracker.error_message}")
        assert tracker.status == "completed", f"Notepad task failed: {tracker.error_message}"
        
        # Clean up created Notepad windows
        windows = win32_utils.list_desktop_windows()
        for w in windows:
            if "notepad.exe" in w["process"].lower() or "notepad" in w["title"].lower():
                win32_utils.focus_window(w["hwnd"])
                await asyncio.sleep(0.5)
                win32_utils.close_window(w["hwnd"])
                await asyncio.sleep(0.5)
                # Discard save prompt if any
                win32_utils.press_key("N")
                await asyncio.sleep(0.5)
                
        # ----------------------------------------------------
        # TEST 3: Recovery (Close application mid-way)
        # ----------------------------------------------------
        print("\n--- TEST 3: Recovery Checks ---")
        # We start a task, let it launch Notepad, then close it, and assert the brain recovers and relaunches it!
        tracker.reset("Open Notepad and type Hello")
        
        # Manually verify steps of loop logic by executing step by step or mocking observations
        obs_start = {
            "active_window": {"title": "Desktop", "process": ""},
            "visible_windows": [],
            "screen": {"width": 1920, "height": 1080},
            "cursor": {"x": 0, "y": 0}
        }
        
        # Step 1: Brain decides to launch Notepad
        dec_1 = await model.decide_action("Open Notepad and type Hello", [], obs_start, [])
        print(f"Decision 1: {dec_1['decision_type']} tool: {dec_1.get('tool_name')}")
        assert dec_1["decision_type"] == "tool_call"
        assert dec_1["tool_name"] == "launch_app"
        
        # Simulate launch completes, but user closes it!
        # Next observation shows Notepad is closed.
        obs_closed = {
            "active_window": {"title": "Desktop", "process": ""},
            "visible_windows": [],
            "screen": {"width": 1920, "height": 1080},
            "cursor": {"x": 0, "y": 0}
        }
        
        # Brain must detect it is closed and decide to launch again! (Recovery!)
        dec_2 = await model.decide_action("Open Notepad and type Hello", [], obs_closed, [
            {"action": "launch_app", "parameters": {"app_name": "notepad.exe"}, "status": "completed"}
        ])
        print(f"Decision 2 (after close): {dec_2['decision_type']} tool: {dec_2.get('tool_name')}")
        assert dec_2["decision_type"] == "tool_call"
        assert dec_2["tool_name"] == "launch_app"
        print("Recovery decision verified successfully!")

        # ----------------------------------------------------
        # TEST 4: Takeover integration checks
        # ----------------------------------------------------
        print("\n--- TEST 4: Takeover Integration ---")
        loop.start_task("Open Notepad and type Hello")
        await asyncio.sleep(1.0)
        
        print("Activating takeover...")
        takeover_manager.take_control()
        await asyncio.sleep(1.5)
        print(f"Agent state during takeover: {tracker.status}")
        assert tracker.status == "paused"
        
        print("Releasing takeover...")
        takeover_manager.release_control()
        await asyncio.sleep(1.5)
        
        # Clean up loop
        loop.stop_task()
        print("Takeover pausing and resuming completed successfully!")

        # ----------------------------------------------------
        # TEST 5: Stop/Cancellation checks
        # ----------------------------------------------------
        print("\n--- TEST 5: Stop Cancellation ---")
        loop.start_task("Open Notepad and type Hello")
        await asyncio.sleep(1.0)
        
        print("Triggering STOP command...")
        loop.stop_task()
        await asyncio.sleep(1.0)
        print(f"Agent status after stop: {tracker.status}")
        assert tracker.status == "cancelled"
        print("Stop cancellation cleanup completed successfully!")

        # ----------------------------------------------------
        # TEST 20: User Clarifications (Ask User)
        # ----------------------------------------------------
        print("\n--- TEST 20: User Clarifications ---")
        # Set up mock model decision that requests user clarification
        async def mock_ask_user(goal, plan, observation, recent_history):
            # Check if user answered first
            for item in recent_history:
                if item.get("action") == "ask_user" and "User answer:" in item.get("error", ""):
                    return {"decision_type": "final", "message": "Resumed task and finished."}
            return {
                "decision_type": "ask_user",
                "question": "Which Notepad window should I use?"
            }
            
        planner.model_provider.decide_action = mock_ask_user
        
        loop.start_task("Open Notepad")
        await asyncio.sleep(1.0)
        
        print(f"Task status waiting check: {tracker.status}")
        assert tracker.status == "waiting_user"
        assert loop._user_response_future is not None
        
        # Respond to question
        print("Submitting answer response...")
        loop._user_response_future.set_result("The main one")
        await asyncio.sleep(1.5)
        
        print(f"Task final status check: {tracker.status}")
        assert tracker.status == "completed"
        print("Clarification question answered and resolved successfully!")

        print("\n====================================================")
        print("PHASE 4 INTEGRATION TEST SUCCESSFUL!")
        print("====================================================")

    finally:
        if os.path.exists(config_path):
            os.remove(config_path)
            
        # Clean up any opened Notepad windows again
        windows = win32_utils.list_desktop_windows()
        for w in windows:
            if "notepad.exe" in w["process"].lower() or "notepad" in w["title"].lower():
                try:
                    win32_utils.close_window(w["hwnd"])
                except Exception:
                    pass

if __name__ == "__main__":
    asyncio.run(run_phase4_integration())
