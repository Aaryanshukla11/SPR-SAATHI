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
from agent.control.takeover import TakeoverManager, ControlState

async def run_takeover_integration():
    print("====================================================")
    print("STARTING SPR SAATHI WINDOWS PHASE 5 INTEGRATION TEST")
    print("====================================================")
    
    if sys.platform != "win32":
        print("Skipping integration test: not on Windows OS.")
        return

    # Use clean permissions setup
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integration_permissions_p5.json")
    if os.path.exists(config_path):
        os.remove(config_path)

    try:
        tracker = StateTracker()
        pm = PolicyManager(config_path=config_path)
        pm.update_policy("mouse", "allow")
        pm.update_policy("keyboard", "allow")
        pm.update_policy("applications", "allow")
        
        takeover_manager = TakeoverManager()
        broker = PermissionBroker(pm, tracker)
        tools = get_all_tools()
        executor = ToolExecutor(tools, broker, takeover_manager)
        
        model = ApiModelProvider("Gemini 3.5 Flash")
        planner = RuleBasedPlanner(model)

        async def log_event(ev):
            print(f"[EVENT] ({ev.get('event_type')}) {ev.get('message')}")

        agent_loop = AgentLoop(
            state_tracker=tracker,
            planner=planner,
            executor=executor,
            takeover_manager=takeover_manager,
            broadcast_callback=log_event
        )

        # ----------------------------------------------------
        # 1. Start Task
        # ----------------------------------------------------
        task_desc = "Open Notepad"
        print(f"\n--- Starting task: '{task_desc}' ---")
        agent_loop.start_task(task_desc)

        # Wait a brief moment to let planning execute
        await asyncio.sleep(1.0)
        
        # ----------------------------------------------------
        # 2. Trigger Take Control
        # ----------------------------------------------------
        print("\n--- Triggering Human Takeover ---")
        agent_loop.pause_task_for_takeover()
        
        assert takeover_manager.is_takeover_active, "Takeover state must be active"
        assert tracker.status == "paused", f"Task status must be 'paused', got {tracker.status}"
        assert tracker.takeover_active, "Tracker takeover flag must be True"

        # Verify tool executions are locked/blocked
        lock_check = await executor.execute_action("launch_app", {"app_name": "notepad.exe"})
        assert not lock_check["success"], "Action must fail when takeover is active"
        assert lock_check["error"] == "CONTROL_LOCKED", "Error must be CONTROL_LOCKED"
        print("[OK] Tool-level input lock verified successfully.")

        # Simulate manual user interactions during takeover (safe mouse query)
        x, y = win32_utils.get_cursor_position()
        print(f"User cursor currently at: {x}, {y}")
        
        # ----------------------------------------------------
        # 3. Release Control
        # ----------------------------------------------------
        print("\n--- Releasing Human Control ---")
        resumed = await agent_loop.resume_task_after_takeover()
        assert resumed, "Resume task must succeed"
        
        # Verify takeover state reset
        assert not takeover_manager.is_takeover_active, "Takeover state must be inactive"
        assert not tracker.takeover_active, "Tracker takeover flag must be False"
        
        # Wait a moment for planning/execution to continue
        await asyncio.sleep(2.0)

        # ----------------------------------------------------
        # 4. Stop Task During Loop
        # ----------------------------------------------------
        print("\n--- Stopping Task ---")
        agent_loop.stop_task()
        await asyncio.sleep(1.0)
        assert tracker.status == "cancelled", f"Expected cancelled status, got {tracker.status}"
        print("[OK] Task stop verification passed.")

        print("\n====================================================")
        print("WINDOWS PHASE 5 INTEGRATION TEST PASSED SUCCESSFULLY!")
        print("====================================================")

    finally:
        if os.path.exists(config_path):
            os.remove(config_path)

if __name__ == "__main__":
    asyncio.run(run_takeover_integration())
