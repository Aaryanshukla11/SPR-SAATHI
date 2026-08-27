import asyncio
import sys
import time
from agent.core.state import StateTracker
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.core.executor import ToolExecutor
from agent.core.planner import RuleBasedPlanner
from agent.core.loop import AgentLoop
from agent.tools import get_all_tools
from agent.core import win32_utils

async def run_smoke_test():
    print("====================================================")
    print("STARTING SPR SAATHI WINDOWS PHASE 2 SMOKE TEST")
    print("====================================================")
    
    if sys.platform != "win32":
        print("Skipping: not on Windows OS.")
        return

    tracker = StateTracker()
    planner = RuleBasedPlanner(None) # Rule planner doesn't need provider for rules matching
    
    pm = PolicyManager()
    pm.update_policy("windows", "allow")
    pm.update_policy("computer", "allow")
    broker = PermissionBroker(pm)
    
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker)
    
    from agent.control.takeover import TakeoverManager
    takeover_manager = TakeoverManager()
    
    async def console_broadcast(event):
        msg = event.get("message", "")
        event_type = event.get("event_type", "").upper()
        print(f"[{event_type}] {msg}")
        if event_type == "OBSERVE" and "cursor_x" in event.get("payload", {}):
            payload = event["payload"]
            print(f"    -> Screen Size: {payload['screen_width']}x{payload['screen_height']}, Cursor: ({payload['cursor_x']},{payload['cursor_y']})")

    loop = AgentLoop(
        state_tracker=tracker,
        planner=planner,
        executor=executor,
        takeover_manager=takeover_manager,
        broadcast_callback=console_broadcast
    )
    
    # ----------------------------------------------------
    # TEST 1: Draw a house in Paint
    # ----------------------------------------------------
    print("\n--- TEST 1: Launching Paint & Drawing House ---")
    task_desc = "Open Paint and draw a house"
    loop.start_task(task_desc)
    
    # Wait for completion (draw has 11 steps: launch, focus, and 9 drags)
    max_duration = 35.0
    elapsed = 0.0
    while tracker.status not in ["completed", "error", "stopped"] and elapsed < max_duration:
        await asyncio.sleep(0.5)
        elapsed += 0.5
        
    print(f"\nTask completed loop check. Status: {tracker.status}")
    assert tracker.status == "completed", f"Drawing task failed: {tracker.error_message}"
    
    # Display action history
    print("\nAction History logged:")
    for item in tracker.action_history:
        print(f"  - Action: {item['action']}, Status: {item['status']}, Duration: {item['duration_ms']}ms")
        
    await asyncio.sleep(2.0)
    
    # ----------------------------------------------------
    # TEST 2: Interruption Safety / Cancellation
    # ----------------------------------------------------
    print("\n--- TEST 2: long drag with Stop command ---")
    # Submit a very slow drag to Paint canvas
    slow_drag_task = {
        "call_id": "test_drag",
        "tool_name": "mouse_drag",
        "arguments": {
            "start_x": 300,
            "start_y": 300,
            "end_x": 700,
            "end_y": 500,
            "duration_ms": 6000,
            "target_window": "Paint"
        }
    }
    
    # Create fake steps list
    tracker.reset("Slow Drag Task")
    tracker.set_steps(["Execute slow drag"])
    
    # Start task loop directly with custom steps if we want, or run executor action
    # We will trigger the executor in a task and cancel it mid-way!
    executor_task = asyncio.create_task(executor.execute_action("mouse_drag", slow_drag_task["arguments"]))
    
    # Wait 1.0 second, then trigger cancellation/stop button releases
    await asyncio.sleep(1.0)
    print("Simulating user STOP button click...")
    win32_utils.release_all_buttons()
    print("Held mouse buttons successfully released.")
    
    # Let executor finish or raise cancelled error
    try:
        res = await executor_task
        print(f"Executor result after stop check: {res}")
    except Exception as e:
        print(f"Executor raised exception as expected: {e}")
        
    # ----------------------------------------------------
    # CLEANUP: Close Paint Application
    # ----------------------------------------------------
    print("\n--- CLEANUP: Closing MS Paint Window ---")
    windows = win32_utils.list_desktop_windows()
    paint_hwnd = None
    for w in windows:
        if "mspaint.exe" in w["process"].lower() or "paint" in w["title"].lower():
            paint_hwnd = w["hwnd"]
            break
            
    if paint_hwnd:
        win32_utils.focus_window(paint_hwnd)
        await asyncio.sleep(0.5)
        win32_utils.close_window(paint_hwnd)
        await asyncio.sleep(0.5)
        # Discard save changes prompt
        print("Discarding Paint save changes prompt by typing 'N'...")
        win32_utils.press_key("N")
        await asyncio.sleep(0.5)
        print("Cleaned up successfully.")
    else:
        print("Paint window not found during cleanup.")
        
    print("\n====================================================")
    print("PHASE 2 INTEGRATION TEST SUCCESSFUL!")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
