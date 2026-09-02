import asyncio
import datetime
import time
from typing import Dict, Any, Callable, Optional, List
from .state import StateTracker
from .planner import BasePlanner
from .executor import ToolExecutor
from agent.control.takeover import TakeoverManager
from agent.core import win32_utils
from agent.core.vision import SCREEN_OBSERVER
from agent.models.base import validate_model_decision
from agent.core.trace import ExecutionTracer

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
        self._user_response_future: Optional[asyncio.Future] = None
        self.tracer: Optional[ExecutionTracer] = None
        
        # Safety Limits (Requirement 26)
        self.max_steps = 50
        self.max_retries_per_step = 3
        self.max_replans = 10
        self.max_task_duration_seconds = 600.0  # 10 minutes

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
        asyncio.create_task(self._emit_event("task.created", f"Started task: {task_description}"))

    def stop_task(self):
        self._cancellation_requested = True
        self.state_tracker.update_status("cancelled")
        self.state_tracker.cancel_all_steps()
        
        # Release any mouse buttons held by the AI on cancel
        win32_utils.release_all_buttons()
        
        # Resolve any waiting user future
        if self._user_response_future and not self._user_response_future.done():
            self._user_response_future.cancel()
            
        if hasattr(self.executor, "permission_broker"):
            self.executor.permission_broker.cancel_all_pending()

        if self._running_task and not self._running_task.done():
            self._running_task.cancel()
        asyncio.create_task(self._emit_event("task.cancelled", "Task was cancelled/stopped by user."))

    def pause_task_for_takeover(self):
        """
        Immediately pauses the current task.
        Cancels the running loop task to interrupt active operations,
        but does NOT reset the state tracker (maintaining task_id and state).
        """
        if not self._running_task or self._running_task.done():
            # If not running, check if it's already paused or idle
            self.takeover_manager.take_control()
            self.state_tracker.takeover_active = True
            self.state_tracker.update_status("paused")
            return

        # Trigger takeover state in manager
        self.takeover_manager.take_control()
        
        # Update tracker status
        self.state_tracker.takeover_active = True
        self.state_tracker.update_status("paused")
        
        # Release any mouse buttons immediately
        win32_utils.release_all_buttons()
        
        # Resolve user response futures if any
        if self._user_response_future and not self._user_response_future.done():
            self._user_response_future.cancel()

        if hasattr(self.executor, "permission_broker"):
            self.executor.permission_broker.cancel_all_pending()

        # Cancel the running task to raise CancelledError instantly
        self._running_task.cancel()
        
        asyncio.create_task(self._emit_event("task.paused", "Takeover active: execution paused by user."))

    async def resume_task_after_takeover(self) -> bool:
        """
        Resumes task execution after takeover is released.
        Performs re-observation, plan revalidation, and replanning before resuming AI_CONTROL.
        """
        if self.state_tracker.status in ["completed", "failed", "cancelled", "stopped"]:
            return False

        # Transitioning state
        self.takeover_manager.release_control()
        self.state_tracker.takeover_active = False
        
        self.state_tracker.update_status("resuming")
        await self._emit_event("task.resuming", "Transitioning back to AI control. Re-observing desktop state...")
        
        # 1. State Re-observation via ScreenObserver
        obs = SCREEN_OBSERVER.capture_observation(task_id=self.state_tracker.task_id)
        self.state_tracker.update_computer_state(obs)
        await self._emit_event("control.reobservation_completed", "Re-observation completed.", obs)
        
        # 2. Plan Revalidation / Compare state
        task_desc = self.state_tracker.current_task or ""
        reval_outcome = await self.planner.revalidate_plan(
            task=task_desc,
            plan=self.state_tracker.steps,
            observation=obs,
            history=self.state_tracker.action_history
        )
        
        await self._emit_event("status_change", f"Plan revalidation outcome: {reval_outcome}")
        
        # 3. Action Invalidation & Replanning
        if reval_outcome == "completed":
            self.state_tracker.update_status("completed")
            await self._emit_event("task.completed", "Revalidation determined the goal is already completed!")
            return True
        elif reval_outcome == "ambiguous":
            self.state_tracker.update_status("waiting_user")
            await self._emit_event("task.waiting_user", "Revalidation state ambiguous. Clarification required.", {"question": "State is ambiguous after takeover. Do you want me to proceed?"})
            return True
        elif reval_outcome == "replan":
            self.state_tracker.update_status("planning")
            await self._emit_event("task.planning", "Re-planning checklist based on new observation...")
            new_steps = self.planner.create_high_level_plan(task_desc)
            self.state_tracker.set_structured_steps(new_steps)
            await self._emit_event("task.plan_updated", "Re-planned checklist generated.", {"steps": new_steps})
            await asyncio.sleep(0.5)

        # 4. Spawn new loop task continuing from same state
        self._cancellation_requested = False
        self._running_task = asyncio.create_task(self._loop(task_desc))
        await self._emit_event("task.resumed", "AI control active: loop execution resumed.")
        return True

    async def _loop(self, task: str):
        start_task_time = time.time()
        consecutive_replans = 0
        step_attempts: Dict[str, int] = {}
        
        # Initialize generic observational tracer
        self.tracer = ExecutionTracer(task)

        # Generate initial high-level plan (Requirement 12)
        self.state_tracker.update_status("planning")
        await self._emit_event("task.planning", "Decomposing goal into plan checklist...")
        initial_steps = self.planner.create_high_level_plan(task)
        self.state_tracker.set_structured_steps(initial_steps)
        await self._emit_event("task.plan_updated", "High-level plan generated.", {"steps": initial_steps})
        await asyncio.sleep(0.5)

        try:
            while True:
                # 1. Bounded Safety Limits check (Requirement 26)
                elapsed_time = time.time() - start_task_time
                if elapsed_time > self.max_task_duration_seconds:
                    raise TimeoutError(f"Task exceeded maximum duration limit of {self.max_task_duration_seconds}s.")
                    
                if self.state_tracker.attempt_count >= self.max_steps:
                    raise RuntimeError(f"Task aborted: exceeded maximum step count limit of {self.max_steps}.")

                if consecutive_replans >= self.max_replans:
                    raise RuntimeError(f"Task aborted: exceeded consecutive replans limit of {self.max_replans}.")

                # 2. Takeover Check (Requirement 18)
                if self.takeover_manager.is_takeover_active:
                    self.state_tracker.update_status("paused")
                    win32_utils.release_all_buttons()
                    await self._emit_event("task.paused", "Takeover active: execution paused by user.")
                    
                    # Wait until user releases control
                    await self.takeover_manager.wait_if_takeover()
                    
                    self.state_tracker.update_status("running")
                    await self._emit_event("task.resumed", "Takeover released: resuming execution loop...")
                    
                    # Re-observe state immediately after takeover
                    active_window = win32_utils.get_active_window_details()
                    visible_windows = win32_utils.list_desktop_windows()
                    screen_w, screen_h = win32_utils.get_screen_size()
                    cursor_x, cursor_y = win32_utils.get_cursor_position()
                    
                    obs = {
                        "active_window": active_window,
                        "visible_windows": visible_windows,
                        "screen": {"width": screen_w, "height": screen_h},
                        "cursor": {"x": cursor_x, "y": cursor_y}
                    }
                    self.state_tracker.update_computer_state(obs)
                    
                    # Force replanning
                    self.state_tracker.update_status("planning")
                    await self._emit_event("task.planning", "Re-planning high-level checklist after takeover...")
                    new_steps = self.planner.create_high_level_plan(task)
                    self.state_tracker.set_structured_steps(new_steps)
                    await self._emit_event("task.plan_updated", "Re-planned checklist.", {"steps": new_steps})
                    consecutive_replans += 1
                    continue

                if self._cancellation_requested:
                    self.state_tracker.update_status("cancelled")
                    return

                # 3. OBSERVE BEFORE ACTION (Visual & Structural Observation)
                self.state_tracker.update_status("running")
                obs_before = SCREEN_OBSERVER.capture_observation(task_id=self.state_tracker.task_id)
                self.state_tracker.update_computer_state(obs_before)
                
                active_window = obs_before.get("active_window")
                obs_message = f"Active window: '{active_window.get('title') if active_window else 'Desktop'}'"
                if obs_before.get("image_available"):
                    obs_message += " [Visual Screen Captured]"
                await self._emit_event("task.observation", f"Observed state: {obs_message}", obs_before)

                if self.tracer:
                    self.tracer.start_step(self.state_tracker.attempt_count + 1, obs_before, obs_message)

                # 4. SELECT NEXT ACTION / DECISION (Multimodal Visual Reasoning)
                model = self.planner.model_provider
                await self._emit_event("status_change", "Thinking with visual context...")
                
                from agent.core.schema import get_tools_schema
                try:
                    num_tools = len(get_tools_schema())
                except Exception:
                    num_tools = 0
                print(f"[DEVELOPMENT LOG] === MODEL_REQUEST ===")
                print(f"  Provider: {model.__class__.__name__}")
                print(f"  Model: {model.model_name}")
                print(f"  Supports Vision: {getattr(model, 'supports_vision', False)}")
                print(f"  Visual Image Attached: {bool(obs_before.get('image_base64'))}")
                print(f"  Number of Tools: {num_tools}")
                
                decision = await model.decide_action(
                    goal=task,
                    plan=self.state_tracker.steps,
                    observation=obs_before,
                    recent_history=self.state_tracker.action_history,
                    image_base64=obs_before.get("image_base64")
                )
                
                # Generic model decision tracing (observational only)
                if self.tracer:
                    self.tracer.record_model_decision(decision.get("_raw_response", decision), decision)
                
                # 5. VALIDATION (Requirement 3 & 10)
                is_valid, err_msg = validate_model_decision(decision)
                if not is_valid:
                    raise ValueError(f"Model returned invalid decision: {err_msg}")
                    
                print(f"[DEVELOPMENT LOG] === MODEL_RESPONSE ===")
                print(f"  Decision Type: {decision.get('decision_type')}")
                if decision.get("decision_type") == "tool_call":
                    print(f"  Tool Call: {decision.get('tool_name')}")
                    import json
                    print(f"  Tool Arguments: {json.dumps(decision.get('arguments'))}")
                    
                await self._emit_event("task.decision", f"Selected action type: {decision['decision_type']}", decision)

                # 6. DECISION ROUTER
                dtype = decision["decision_type"]
                
                # --- final decision ---
                if dtype == "final":
                    self.state_tracker.update_status("completed")
                    await self._emit_event("task.completed", decision.get("message", "Task finished successfully!"))
                    return
                    
                # --- replan decision ---
                elif dtype == "replan":
                    self.state_tracker.update_status("planning")
                    await self._emit_event("task.replanning", f"Replanning requested: {decision.get('reason')}")
                    
                    new_steps = self.planner.create_high_level_plan(task)
                    self.state_tracker.set_structured_steps(new_steps)
                    await self._emit_event("task.plan_updated", "Plan re-decomposed.", {"steps": new_steps})
                    consecutive_replans += 1
                    await asyncio.sleep(0.5)
                    continue
                    
                # --- ask_user decision ---
                elif dtype == "ask_user":
                    question = decision.get("question", "Agent requested clarification.")
                    self.state_tracker.update_status("waiting_user")
                    await self._emit_event("task.waiting_user", f"Question: {question}", {"question": question})
                    
                    # Create future to wait for user answer
                    self._user_response_future = asyncio.get_running_loop().create_future()
                    try:
                        # Default user answer timeout is 60s (Requirement 20)
                        user_text = await asyncio.wait_for(self._user_response_future, timeout=60.0)
                        
                        # Add user answer to history memory
                        self.state_tracker.add_action_history("ask_user", {"question": question}, "completed", error_message=f"User answer: {user_text}")
                        await self._emit_event("status_change", f"Resuming task with answer: {user_text}")
                    except asyncio.TimeoutError:
                        self._user_response_future = None
                        raise TimeoutError(f"User did not answer within 60 seconds.")
                    continue
                    
                # --- wait decision ---
                elif dtype == "wait":
                    wait_seconds = float(decision.get("duration_seconds", 2.0))
                    # Avoid unbounded wait
                    wait_seconds = min(wait_seconds, 15.0)
                    
                    await self._emit_event("status_change", f"Waiting for {wait_seconds} seconds...")
                    await asyncio.sleep(wait_seconds)
                    continue

                # --- tool_call decision ---
                elif dtype == "tool_call":
                    tool_name = decision.get("tool_name", "")
                    args = decision.get("arguments", {})
                    call_id = f"step_{self.state_tracker.attempt_count + 1}"
                    
                    # Find active step to check progress checklist
                    active_step_id = None
                    for step in self.state_tracker.steps:
                        if step["status"] == "pending":
                            active_step_id = step["step_id"]
                            break
                    if not active_step_id and self.state_tracker.steps:
                        active_step_id = self.state_tracker.steps[-1]["step_id"]

                    # 1. Action Validation (Requirement 10)
                    from agent.core.action_validator import validate_action
                    is_valid, err_msg = validate_action(tool_name, args)
                    if not is_valid:
                        err_text = f"Action validation rejected: {err_msg}"
                        await self._emit_event("tool.failed", err_text, {"tool": tool_name})
                        # Fail-safe record to history
                        self.state_tracker.add_action_history(tool_name, args, "failed", err_text, 0)
                        raise ValueError(err_text)
                    
                    # 2. Loop Protection Stuck Limits (Requirement 27)
                    recent_actions = self.state_tracker.action_history[-3:]
                    if len(recent_actions) >= 3 and all(a.get("action") == tool_name and a.get("parameters") == args and a.get("status") == "failed" for a in recent_actions):
                        raise RuntimeError(f"Loop protection triggered: Repeated execution failures for tool '{tool_name}' with arguments {args}.")

                    # 3. Check permission & Act
                    self.state_tracker.update_status("waiting_permission")
                    await self._emit_event("tool.requested", f"Action request: {tool_name}", {"tool_call": {"tool_name": tool_name, "arguments": args, "call_id": call_id}})
                    
                    if active_step_id:
                        self.state_tracker.start_step(active_step_id, {"tool_name": tool_name, "arguments": args, "call_id": call_id})
                    
                    self.state_tracker.update_status("acting")
                    await self._emit_event("tool.started", f"Acting: executing {tool_name}")
                    
                    active_win_before = win32_utils.get_active_window_details()
                    start_time = time.time()
                    result = await self.executor.execute_action(tool_name, args, call_id)
                    duration_ms = int((time.time() - start_time) * 1000)
                    active_win_after = win32_utils.get_active_window_details()

                    # Compute internal coordinate transformation if any was performed
                    transformed_coords = None
                    if any(k in args for k in ("x", "y", "start_x", "start_y")):
                        _, transformed_coords, _ = win32_utils.resolve_coordinates(args)

                    if self.tracer:
                        self.tracer.record_tool_execution(
                            tool_name,
                            args,
                            transformed_coords,
                            active_win_before,
                            active_win_after,
                            result,
                            duration_ms
                        )

                    print(f"[DEVELOPMENT LOG] === TOOL_RESULT ===")
                    print(f"  Tool: {tool_name}")
                    print(f"  Success: {result.get('success')}")
                    print(f"  Output: {result.get('output')}")
                    print(f"  Error: {result.get('error')}")

                    # 4. OBSERVE AFTER ACTION (Let UI settle & capture updated visual state)
                    self.state_tracker.update_status("verifying")
                    await asyncio.sleep(0.35)
                    
                    obs_after = SCREEN_OBSERVER.capture_observation(task_id=self.state_tracker.task_id)
                    self.state_tracker.update_computer_state(obs_after)

                    self.state_tracker.add_action_history(
                        tool_name, 
                        args, 
                        "completed" if result["success"] else "failed", 
                        result.get("error"), 
                        duration_ms,
                        output=result.get("output"),
                        obs_before=obs_before,
                        obs_after=obs_after
                    )

                    after_win = obs_after.get("active_window")
                    after_win_title = after_win.get("title", "Desktop") if after_win else "Desktop"
                    await self._emit_event(
                        "task.observation_after", 
                        f"Observation after {tool_name}: Active window '{after_win_title}'", 
                        obs_after
                    )

                    # Deterministic validation for launch/focus/mouse verification
                    if result["success"]:
                        if tool_name == "launch_app":
                            target_name = args.get("app_name", "").lower()
                            clean_name = target_name.replace(".exe", "")
                            matched = False
                            for _ in range(12):
                                windows = win32_utils.list_desktop_windows()
                                if any(clean_name in w["process"].lower() or clean_name in w["title"].lower() for w in windows):
                                    matched = True
                                    break
                                await asyncio.sleep(0.5)
                            if not matched:
                                result["success"] = False
                                result["error"] = f"Verification failed: Process/window for '{target_name}' was not detected after launching."
                                
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
                                result["error"] = "Verification failed: Target window was not focused."

                        elif tool_name in ("mouse_drag", "draw_line", "draw_polyline", "draw_rectangle", "draw_shape"):
                            # Distinguish ACTION_SUCCESS (OS input injected) from RESULT_SUCCESS (pixels visually modified)
                            if result.get("result_success") is False or result.get("verification_status") == "verification_failed":
                                result["success"] = False
                                if not result.get("error"):
                                    result["error"] = "Visual verification failed: No visible change detected on the target canvas."

                    # Verify outcome
                    if result["success"]:
                        await self._emit_event("tool.completed", f"Action completed: {tool_name}", {"duration_ms": duration_ms})
                        if active_step_id:
                            self.state_tracker.complete_step(active_step_id)
                        consecutive_replans = 0 # reset replans on success
                    else:
                        await self._emit_event("tool.failed", f"Action failed: {result['error']}", {"duration_ms": duration_ms})
                        if active_step_id:
                            self.state_tracker.fail_step(active_step_id)
                            
                        # Increment step retry attempt counts
                        step_id = active_step_id or "generic"
                        step_attempts[step_id] = step_attempts.get(step_id, 0) + 1
                        if step_attempts[step_id] >= self.max_retries_per_step:
                            logger.warning(f"Step '{step_id}' reached max attempts ({self.max_retries_per_step}). Forcing replan.")
                            await self._emit_event("task.step_limit_reached", f"Step '{step_id}' reached retry limit ({self.max_retries_per_step}). Replanning.")
                            step_attempts[step_id] = 0 # reset attempts for new attempt phase
                            consecutive_replans += 1
                            if consecutive_replans > self.max_replans:
                                raise RuntimeError(f"Step '{step_id}' failed consecutively {self.max_retries_per_step} times. Aborting task.")

                    # Increment total attempts count
                    self.state_tracker.attempt_count += 1
                    await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            if self.takeover_manager.is_takeover_active:
                # Execution paused for human takeover; preserve checklist state & task ID
                self.state_tracker.update_status("paused")
                win32_utils.release_all_buttons()
                await self._emit_event("control.takeover_started", "Takeover active: AI loop paused safely.")
            else:
                self.state_tracker.update_status("cancelled")
                self.state_tracker.cancel_all_steps()
                win32_utils.release_all_buttons()
                await self._emit_event("task.cancelled", "Autonomous task cancelled.")
        except Exception as e:
            self.state_tracker.update_status("failed")
            self.state_tracker.error_message = str(e)
            win32_utils.release_all_buttons()
            await self._emit_event("task.failed", f"Autonomous task failed: {str(e)}", {"error": str(e)})
        finally:
            # Clean up temporary screenshots if task is finished or cancelled
            try:
                SCREEN_OBSERVER.lifecycle_manager.cleanup_task_screenshots(self.state_tracker.task_id)
            except Exception:
                pass
            if self.tracer:
                try:
                    self.tracer.save_trace("agent_execution_trace.json")
                except Exception:
                    pass
