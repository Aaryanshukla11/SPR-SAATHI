import pytest
import os
import json

from agent.core.trace import ExecutionTracer


# ============================================================================
# 1. COMPLETE TRACES & CORRELATION IDS TESTS
# ============================================================================

def test_execution_tracer_correlation_ids():
    """Verify ExecutionTracer links task_id and action_id across steps."""
    tracer = ExecutionTracer(task_goal="Create presentation", task_id="task_corr_101")
    assert tracer.task_id == "task_corr_101"

    # Step 1
    tracer.start_step(step_number=1, observation={"win": "Desktop"}, action_id="act_step_1")
    tracer.record_model_decision('{"decision_type": "tool_call"}', {"decision_type": "tool_call", "tool_name": "launch_app"})
    tracer.record_tool_execution(
        tool_name="launch_app",
        received_arguments={"app_name": "notepad.exe"},
        transformed_coordinates=None,
        active_window_before={"title": "Desktop"},
        active_window_after={"title": "Notepad"},
        result={"success": True, "output": "Launched"},
        duration_ms=250
    )
    tracer.record_verification(status="verified_success", details={"window_detected": True})
    tracer.finalize_step()

    trace = tracer.get_trace()
    assert trace["total_steps"] == 1
    step = trace["steps"][0]
    assert step["task_id"] == "task_corr_101"
    assert step["action_id"] == "act_step_1"
    assert step["tool_execution"]["success"] is True
    assert step["verification"]["status"] == "verified_success"


# ============================================================================
# 2. ERROR PROPAGATION & RECOVERY ATTEMPTS TRACING
# ============================================================================

def test_tracer_error_propagation_and_recovery():
    """Verify tracer records errors, failure classifications, and recovery strategies."""
    tracer = ExecutionTracer(task_goal="Process file", task_id="task_err_202")

    tracer.start_step(step_number=1, observation={}, action_id="act_fail_1")
    tracer.record_tool_execution(
        tool_name="read_file",
        received_arguments={"path": "missing.txt"},
        transformed_coordinates=None,
        active_window_before=None,
        active_window_after=None,
        result={"success": False, "error": "File not found"},
        duration_ms=45
    )
    tracer.record_verification(status="verification_failed", details={"file_exists": False})
    tracer.record_recovery_attempt(failure_type="file_failure", strategy="alternative_tool", reason="File missing")
    tracer.finalize_step()

    diag = tracer.export_diagnostic_summary()
    assert diag["task_id"] == "task_err_202"
    assert diag["failed_steps_count"] == 1
    assert len(diag["failures"]) == 1
    assert diag["failures"][0]["tool"] == "read_file"
    assert diag["failures"][0]["recovery"]["strategy"] == "alternative_tool"


# ============================================================================
# 3. TRACE SERIALIZATION & DISK PERSISTENCE
# ============================================================================

def test_tracer_json_serialization(tmp_path):
    """Verify save_trace persists readable JSON with all diagnostic keys."""
    trace_path = tmp_path / "execution_trace.json"
    tracer = ExecutionTracer(task_goal="Serialization test", task_id="task_save_303")

    tracer.start_step(step_number=1, observation={"active": "Paint"})
    tracer.record_tool_execution(
        tool_name="mouse_click",
        received_arguments={"x": 50, "y": 50},
        transformed_coordinates={"x": 50, "y": 50},
        active_window_before=None,
        active_window_after=None,
        result={"success": True},
        duration_ms=10
    )
    tracer.finalize_step()

    tracer.save_trace(str(trace_path))
    assert os.path.exists(trace_path)

    with open(trace_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["task_id"] == "task_save_303"
    assert data["total_steps"] == 1
    assert data["steps"][0]["tool_execution"]["tool_name"] == "mouse_click"
