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

async def run_phase3_integration():
    print("====================================================")
    print("STARTING SPR SAATHI WINDOWS PHASE 3 INTEGRATION TEST")
    print("====================================================")
    
    if sys.platform != "win32":
        print("Skipping: not on Windows OS.")
        return

    # Use a temp config file for isolation
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integration_permissions.json")
    if os.path.exists(config_path):
        os.remove(config_path)

    try:
        # Initialize
        tracker = StateTracker()
        pm = PolicyManager(config_path=config_path)
        broker = PermissionBroker(pm, tracker)
        tools = get_all_tools()
        executor = ToolExecutor(tools, broker)
        planner = RuleBasedPlanner(None)
        
        from agent.control.takeover import TakeoverManager
        takeover_manager = TakeoverManager()

        loop = AgentLoop(
            state_tracker=tracker,
            planner=planner,
            executor=executor,
            takeover_manager=takeover_manager,
            broadcast_callback=None
        )

        # ----------------------------------------------------
        # TEST A & B: Specific App Override Block (Notepad -> DENY)
        # ----------------------------------------------------
        print("\n--- TEST A & B: Notepad -> DENY Override ---")
        pm.update_policy("applications", "allow")
        pm.update_app_policy("notepad.exe", "deny")
        
        loop.start_task("Open Notepad")
        
        # Wait for task completion/failure
        await asyncio.sleep(2.0)
        print(f"Notepad task status: {tracker.status}, Error: {tracker.error_message}")
        assert tracker.status == "error"
        assert "Permission denied" in tracker.error_message
        print("Notepad launch blocked successfully!")

        # ----------------------------------------------------
        # TEST C: PowerShell Category Block (PowerShell -> DENY, Terminal -> ALLOW)
        # ----------------------------------------------------
        print("\n--- TEST C: PowerShell -> DENY vs Terminal -> ALLOW ---")
        pm.update_policy("terminal", "allow")
        pm.update_policy("powershell", "deny")
        
        # Execute PowerShell
        pwsh_res = await executor.execute_action("powershell", {"script": "echo Hello"})
        print(f"PowerShell execution success: {pwsh_res['success']}, Error: {pwsh_res.get('error')}")
        assert pwsh_res["success"] is False
        assert "Permission denied" in pwsh_res["error"]
        
        # Execute CMD
        cmd_res = await executor.execute_action("cmd", {"command": "echo Hello"})
        print(f"CMD execution success: {cmd_res['success']}")
        assert cmd_res["success"] is True
        print("PowerShell blocked independently from Terminal!")

        # ----------------------------------------------------
        # TEST G: Config Persistence Check
        # ----------------------------------------------------
        print("\n--- TEST G: Configuration Persistence ---")
        pm.update_policy("filesystem", "allow")
        pm.update_app_policy("paint.exe", "prompt")
        
        # Instantiate second policy manager reloading same json config path
        pm2 = PolicyManager(config_path=config_path)
        print(f"Reloaded filesystem level: {pm2.policies['filesystem']}")
        print(f"Reloaded paint override level: {pm2.app_policies['paint.exe']}")
        assert pm2.policies["filesystem"] == "allow"
        assert pm2.app_policies["paint.exe"] == "prompt"
        print("Configuration states persisted cleanly!")

        # ----------------------------------------------------
        # TEST Timeout: Unanswered Prompts
        # ----------------------------------------------------
        print("\n--- TEST Timeout: Bounded prompt wait ---")
        broker.timeout_seconds = 1.0 # set short timeout
        pm.update_policy("mouse", "prompt")
        
        async def mock_unresponsive_ui(req_id, tool, args):
            print(f"UI prompt notification triggered for request: {req_id}. Simulation unresponsive...")
            
        broker.on_prompt_callback = mock_unresponsive_ui
        
        start_time = asyncio.get_event_loop().time()
        res = await executor.execute_action("mouse_click", {"x": 500, "y": 500, "button": "left"})
        duration = asyncio.get_event_loop().time() - start_time
        
        print(f"Timeout result success: {res['success']}, Error: {res.get('error')}")
        print(f"Timeout waited: {duration:.2f} seconds")
        assert res["success"] is False
        assert "Permission denied" in res["error"]
        print("Prompt timeout completed safely!")

        # ----------------------------------------------------
        # Audit Log Check
        # ----------------------------------------------------
        print("\n--- Audit Logs recorded: ---")
        for log in broker.audit_trail:
            print(f"  - [{log['timestamp']}] Tool: {log['resource']}, Decision: {log['decision']}, Source: {log['source']}")
        assert len(broker.audit_trail) > 0

        print("\n====================================================")
        print("PHASE 3 INTEGRATION TEST SUCCESSFUL!")
        print("====================================================")

    finally:
        if os.path.exists(config_path):
            os.remove(config_path)

if __name__ == "__main__":
    asyncio.run(run_phase3_integration())
