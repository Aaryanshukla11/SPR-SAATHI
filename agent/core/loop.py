import asyncio
import datetime
import time
from typing import Dict, Any, Callable, Optional, List
from .state import StateTracker
from .planner import BasePlanner
from .executor import ToolExecutor
from agent.control.takeover import TakeoverManager
from agent.core import win32_utils

class AgentLoop:
    def __init__(
        self,
        state_tracker: StateTracker,
        planner: BasePlanner,
        executor: ToolExecutor,
        takeover_manager: TakeoverManager,
        broadcast_callback: Optional[Callable] = None
    ):
        self.state_tracker = state_tracker
        self.planner = planner
        self.executor = executor
        self.takeover_manager = takeover_manager
        self.broadcast_callback = broadcast_callback
        
        self._cancellation_requested = False
        self._running_task: Optional[asyncio.Task] = None

    async def _emit_event(self, event_type: str, message: str, payload: Optional[Dict[str, Any]] = None):
        if self.broadcast_callback:
            event = {
                "event_type": event_type,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "task_id": self.state_tracker.task_id,
                "message": message,
                "payload": payload or {}
            }
            await self.broadcast_callback(event)

    def start_task(self, task_description: str):
        if self._running_task and not self._running_task.done():
            raise RuntimeError("An autonomous task is already running.")

        self._cancellation_requested = False
        self.state_tracker.reset(task_description)
        self._running_task = asyncio.create_task(self._loop(task_description))

    def stop_task(self):
        self._cancellation_requested = True
        self.state_tracker.update_status("stopped")
        self.state_tracker.cancel_all_steps()
        
        # Release any mouse buttons held by the AI on cancel
        win32_utils.release_all_buttons()
        
        if self._running_task and not self._running_task.done():
            self._running_task.cancel()
        asyncio.create_task(self._emit_event("stop", "Task was cancelled/stopped by user."))

    async def _loop(self, task: str):
        try:
            # OBSERVE
            self.state_tracker.update_status("observing")
            await self._emit_event("observe", "Observing current computer state...")
            
            # Fetch real window state and screen metrics
            active_window = win32_utils.get_active_window_details()
            screen_w, screen_h = win32_utils.get_screen_size()
            cursor_x, cursor_y = win32_utils.get_cursor_position()
            
            computer_state = {
                "active_window": active_window,
                "screen_width": screen_w,
                "screen_height": screen_h,
                "cursor_x": cursor_x,
                "cursor_y": cursor_y
            }
            self.state_tracker.update_computer_state(computer_state)
            
            if active_window:
                observation = f"Active window: title='{active_window['title']}', process='{active_window['process']}', pid={active_window['pid']}. Screen: {screen_w}x{screen_h}. Cursor: ({cursor_x},{cursor_y})"
            else:
                observation = f"No active window detected (Desktop focused). Screen: {screen_w}x{screen_h}. Cursor: ({cursor_x},{cursor_y})"
                
            await self._emit_event("observe", f"State observed: {observation}", computer_state)
            await asyncio.sleep(0.5)

            # PLAN
            self.state_tracker.update_status("planning")
            await self._emit_event("plan", "Creating execution plan...")
            steps_desc, tool_calls = await self.planner.create_plan(task, observation)
            self.state_tracker.set_steps(steps_desc)
            await self._emit_event("plan", f"Plan created with {len(steps_desc)} steps.", {"steps": steps_desc})
            await asyncio.sleep(0.5)

            # Execution loop
            for i, step in enumerate(self.state_tracker.steps):
                # 1. Takeover Check
                if self.takeover_manager.is_takeover_active:
                    self.state_tracker.update_status("takeover")
                    
                    # Immediately release any mouse buttons currently held by the AI on takeover
                    win32_utils.release_all_buttons()
                    
                    await self._emit_event("takeover", "Human takeover active. Pausing agent loop and releasing inputs.")
                    await self.takeover_manager.wait_if_takeover()
                    
                    # Wake up: Re-observe and Re-plan
                    self.state_tracker.update_status("observing")
                    await self._emit_event("observe", "Resuming from takeover. Re-observing computer state...")
                    
                    active_window = win32_utils.get_active_window_details()
                    screen_w, screen_h = win32_utils.get_screen_size()
                    cursor_x, cursor_y = win32_utils.get_cursor_position()
                    
                    computer_state = {
                        "active_window": active_window,
                        "screen_width": screen_w,
                        "screen_height": screen_h,
                        "cursor_x": cursor_x,
                        "cursor_y": cursor_y
                    }
                    self.state_tracker.update_computer_state(computer_state)
                    
                    if active_window:
                        observation = f"Active window: title='{active_window['title']}', process='{active_window['process']}'. Screen: {screen_w}x{screen_h}. Cursor: ({cursor_x},{cursor_y})"
                    else:
                        observation = f"No active window. Screen: {screen_w}x{screen_h}. Cursor: ({cursor_x},{cursor_y})"
                    
                    self.state_tracker.update_status("planning")
                    await self._emit_event("plan", "Re-planning task after human takeover...")
                    steps_desc, tool_calls = await self.planner.create_plan(task, observation)
                    self.state_tracker.set_steps(steps_desc)
                    await self._emit_event("plan", "New plan created.", {"steps": steps_desc})
                    await asyncio.sleep(0.5)
                    return await self._loop(task)

                # 2. Cancellation Check
                if self._cancellation_requested:
                    self.state_tracker.update_status("stopped")
                    return

                tool_call = tool_calls[i] if i < len(tool_calls) else None
                step_id = step["step_id"]

                # 3. Check permission & Act
                self.state_tracker.start_step(step_id, tool_call)
                self.state_tracker.update_status("checking_permission")
                await self._emit_event("status_change", f"Checking permissions for {step_id}...")

                if tool_call:
                    tool_name = tool_call["tool_name"]
                    args = tool_call["arguments"]
                    call_id = tool_call["call_id"]

                    # Typed Action Protocol Event Emit
                    await self._emit_event("action_requested", f"Action requested: {tool_name}", {"tool_call": tool_call})

                    # Coordinate Validation & Resolution Check BEFORE permission broker
                    from agent.core.action_validator import validate_action
                    is_valid, err_msg = validate_action(tool_name, args)
                    if not is_valid:
                        err_text = f"Action validation rejected: {err_msg}"
                        await self._emit_event("action_failed", err_text)
                        result = {
                            "success": False,
                            "error": err_text,
                            "output": ""
                        }
                    else:
                        await self._emit_event("action_validated", f"Action validated: {tool_name}")
                        await self._emit_event("permission_check", f"Evaluating security rules for {tool_name}")

                        # Act
                        self.state_tracker.update_status("acting")
                        await self._emit_event("act", f"Executing step: {step['description']}", {"tool_call": tool_call})
                        await self._emit_event("action_started", f"Executing tool: {tool_name}")
                        
                        start_time = time.time()
                        result = await self.executor.execute_action(tool_name, args, call_id)
                        duration_ms = int((time.time() - start_time) * 1000)

                        # Update action history
                        self.state_tracker.add_action_history(
                            tool_name, 
                            args, 
                            "completed" if result["success"] else "failed", 
                            result.get("error"), 
                            duration_ms
                        )

                        if result["success"]:
                            await self._emit_event("action_completed", f"Action completed: {tool_name}", {"duration_ms": duration_ms})
                        else:
                            await self._emit_event("action_failed", f"Action failed: {result['error']}", {"duration_ms": duration_ms})

                    # 4. Verify
                    self.state_tracker.update_status("verifying")
                    await self._emit_event("verify", f"Verifying execution of step: {step_id}...")
                    
                    # Update state after action
                    active_window = win32_utils.get_active_window_details()
                    screen_w, screen_h = win32_utils.get_screen_size()
                    cursor_x, cursor_y = win32_utils.get_cursor_position()
                    
                    computer_state = {
                        "active_window": active_window,
                        "screen_width": screen_w,
                        "screen_height": screen_h,
                        "cursor_x": cursor_x,
                        "cursor_y": cursor_y
                    }
                    self.state_tracker.update_computer_state(computer_state)

                    # Deterministic Verification for key tools
                    if result["success"]:
                        if tool_name == "launch_app":
                            target_name = args.get("app_name", "").lower()
                            matched = False
                            for _ in range(6):
                                windows = win32_utils.list_desktop_windows()
                                if any(target_name in w["process"].lower() or target_name.replace(".exe", "") in w["process"].lower() for w in windows):
                                    matched = True
                                    break
                                await asyncio.sleep(0.5)
                            if not matched:
                                result["success"] = False
                                result["error"] = f"Verification failed: Process '{target_name}' was not detected on the desktop after launching."
                                
                        elif tool_name == "focus_window":
                            title_sub = args.get("title_substring", "").lower()
                            proc_name = args.get("process_name", "").lower()
                            matched = False
                            for _ in range(3):
                                active_window = win32_utils.get_active_window_details()
                                if active_window:
                                    title_match = not title_sub or title_sub in active_window["title"].lower()
                                    proc_match = not proc_name or proc_name in active_window["process"].lower()
                                    if title_match and proc_match:
                                        matched = True
                                        break
                                
                                windows = win32_utils.list_desktop_windows()
                                if any((not title_sub or title_sub in w["title"].lower()) and 
                                       (not proc_name or proc_name in w["process"].lower()) for w in windows):
                                    matched = True
                                    break
                                    
                                await asyncio.sleep(0.5)
                            if not matched:
                                result["success"] = False
                                result["error"] = "Verification failed: Target window could not be focused or found on the desktop."

                    if result["success"]:
                        self.state_tracker.complete_step(step_id)
                    else:
                        self.state_tracker.fail_step(step_id)
                        self.state_tracker.update_status("error")
                        self.state_tracker.error_message = result["error"]
                        
                        # Release any buttons currently held by the AI on error
                        win32_utils.release_all_buttons()
                        
                        await self._emit_event("error", f"Task execution failed at step {step_id}: {result['error']}")
                        return
                else:
                    self.state_tracker.complete_step(step_id)
                
                await asyncio.sleep(0.5)

            # Completion
            self.state_tracker.update_status("completed")
            await self._emit_event("task_completed", "Autonomous task completed successfully!")

        except asyncio.CancelledError:
            self.state_tracker.update_status("stopped")
            self.state_tracker.cancel_all_steps()
            win32_utils.release_all_buttons()
        except Exception as e:
            self.state_tracker.update_status("error")
            self.state_tracker.error_message = str(e)
            win32_utils.release_all_buttons()
            await self._emit_event("error", f"An unexpected error occurred in loop: {str(e)}")


