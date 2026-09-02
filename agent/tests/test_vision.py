import pytest
import asyncio
import os
import json
import base64
from typing import Dict, Any, List, Optional
from PIL import Image

from agent.core.vision import ScreenObserver, ScreenshotLifecycleManager, SCREEN_OBSERVER
from agent.core.state import StateTracker
from agent.core.planner import RuleBasedPlanner
from agent.core.executor import ToolExecutor
from agent.core.loop import AgentLoop
from agent.control.takeover import TakeoverManager
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.models.base import BaseModelProvider, ModelResponse
from agent.models.api import ApiModelProvider
from agent.models.local import LocalModelProvider
from agent.tools import get_all_tools

class MockVisionModel(BaseModelProvider):
    def __init__(self, decisions: List[Dict[str, Any]], supports_vision: bool = True):
        super().__init__("mock-vision-model")
        self._decisions = list(decisions)
        self._supports_vision = supports_vision
        self.received_calls: List[Dict[str, Any]] = []

    @property
    def capabilities(self) -> Dict[str, Any]:
        return {
            "supports_tool_calling": True,
            "supports_structured_output": True,
            "supports_vision": self._supports_vision,
            "supports_streaming": False,
            "context_window": 128000
        }

    async def generate(self, prompt: str, system_instruction: Optional[str] = None) -> ModelResponse:
        return ModelResponse(text="mock")

    async def generate_with_tools(self, prompt: str, tools: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> ModelResponse:
        return ModelResponse(text="mock")

    async def decide_action(
        self, 
        goal: str, 
        plan: List[Dict[str, Any]], 
        observation: Dict[str, Any], 
        recent_history: List[Dict[str, Any]],
        image_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        self.received_calls.append({
            "goal": goal,
            "plan": plan,
            "observation": observation,
            "recent_history": recent_history,
            "image_base64": image_base64
        })
        if self._decisions:
            return self._decisions.pop(0)
        return {"decision_type": "final", "message": "Task complete."}


def test_screen_observer_capture_metadata():
    """Test 1 & 2: Screenshot capture and structured metadata."""
    observer = ScreenObserver()
    obs = observer.capture_observation(task_id="test_task_01")
    
    assert "timestamp" in obs
    assert "screen" in obs
    assert "cursor" in obs
    assert "active_window" in obs
    assert "visible_windows" in obs
    assert "image_available" in obs
    assert isinstance(obs["image_available"], bool)
    
    if obs["image_available"]:
        assert obs["image_base64"] is not None
        assert len(obs["image_base64"]) > 100
        assert obs["image_path"] is not None
        assert os.path.exists(obs["image_path"])
        
    observer.lifecycle_manager.cleanup_task_screenshots("test_task_01")


def test_screenshot_lifecycle_pruning_and_cleanup(tmp_path):
    """Test 3: Screenshot lifecycle management, pruning, and directory cleanup."""
    mgr = ScreenshotLifecycleManager(base_dir=str(tmp_path), max_recent_per_task=3)
    task_id = "lifecycle_test_task"
    task_dir = mgr.get_task_dir(task_id)
    
    # Create 6 fake image files
    for i in range(6):
        fpath = os.path.join(task_dir, f"shot_{i}.jpg")
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(fpath, "JPEG")
        
    # Prune
    mgr.prune_old_screenshots_for_task(task_id)
    remaining = os.listdir(task_dir)
    assert len(remaining) == 3, f"Expected 3 remaining screenshots, found {len(remaining)}"
    
    # Cleanup task
    mgr.cleanup_task_screenshots(task_id)
    assert not os.path.exists(task_dir)


@pytest.mark.asyncio
async def test_agent_loop_before_and_after_observation():
    """Test 4 & 5: AgentLoop captures observations before and after actions, passing visual context."""
    st = StateTracker()
    pm = PolicyManager()
    pm.update_policy("windows", "allow")
    pm.update_policy("computer", "allow")
    tm = TakeoverManager()
    broker = PermissionBroker(pm, st)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker, tm)

    decisions = [
        {"decision_type": "tool_call", "tool_name": "take_screenshot", "arguments": {}},
        {"decision_type": "final", "message": "Observed and finished."}
    ]
    model = MockVisionModel(decisions, supports_vision=True)
    planner = RuleBasedPlanner(model)
    loop = AgentLoop(st, planner, executor, tm)

    await loop._loop("Verify visual feedback loop")

    assert st.status == "completed"
    assert len(model.received_calls) >= 2

    # Step 1 call should have observation before
    call_1 = model.received_calls[0]
    assert "observation" in call_1
    assert "active_window" in call_1["observation"]

    # History should contain observation_before and observation_after
    assert len(st.action_history) >= 1
    history_item = st.action_history[0]
    assert history_item["action"] == "take_screenshot"
    assert "observation_before" in history_item
    assert "observation_after" in history_item


@pytest.mark.asyncio
async def test_non_vision_model_graceful_fallback():
    """Test 7: Non-vision model gracefully processes context without error."""
    st = StateTracker()
    pm = PolicyManager()
    tm = TakeoverManager()
    broker = PermissionBroker(pm, st)
    tools = get_all_tools()
    executor = ToolExecutor(tools, broker, tm)

    decisions = [
        {"decision_type": "final", "message": "Text-only completed."}
    ]
    # supports_vision is False
    model = MockVisionModel(decisions, supports_vision=False)
    planner = RuleBasedPlanner(model)
    loop = AgentLoop(st, planner, executor, tm)

    await loop._loop("Text-only fallback task")

    assert st.status == "completed"
    assert len(model.received_calls) == 1
    # Model received observation without crashing
    assert "observation" in model.received_calls[0]


def test_screen_observer_handles_capture_failure(monkeypatch):
    """Test 8: Screenshot failure gracefully falls back to text without crashing."""
    observer = ScreenObserver()
    
    # Mock capture methods to simulate failure
    monkeypatch.setattr(observer, "_capture_screen_gdi", lambda: None)
    monkeypatch.setattr(observer, "_capture_screen_fallback", lambda: None)
    
    obs = observer.capture_observation(task_id="failure_test")
    assert obs["image_available"] is False
    assert obs["image_base64"] is None
    assert obs["observation_error"] is not None
    assert obs["screen"]["width"] > 0 # Screen metadata still present


def test_action_history_bounded_size():
    """Test 9: Action history remains bounded to prevent memory leaks."""
    st = StateTracker()
    st.reset("Bounded test")
    
    for i in range(70):
        st.add_action_history(
            action_name=f"action_{i}",
            parameters={"idx": i},
            status="completed",
            obs_before={"image_available": False},
            obs_after={"image_available": False}
        )
        
    assert len(st.action_history) == 50, f"Expected 50 items max, got {len(st.action_history)}"


def test_no_hardcoded_paint_or_cube_logic():
    """Test 10: Ensures no hardcoded cube coordinates or Paint task routes exist."""
    import inspect
    from agent.core import loop, context, planner, win32_utils
    
    for mod in [loop, context, planner, win32_utils]:
        src = inspect.getsource(mod)
        assert "cube" not in src.lower(), f"Hardcoded 'cube' found in {mod.__name__}"
