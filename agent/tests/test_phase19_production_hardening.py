import pytest
import os
import psutil

from agent.core.production_hardening import (
    MemoryMonitor, CrashRecoveryManager, GracefulShutdownHandler,
    MEMORY_MONITOR, CRASH_RECOVERY
)
from agent.core.state import StateTracker


# ============================================================================
# 1. MEMORY MONITORING & LEAK PREVENTION TESTS
# ============================================================================

def test_memory_monitor_health_check():
    """Verify MemoryMonitor measures process RSS and reports status."""
    mon = MemoryMonitor(warning_threshold_mb=10000.0, critical_threshold_mb=20000.0)
    current_mb = mon.get_current_memory_mb()
    assert current_mb > 0.0

    health = mon.check_memory_health()
    assert health["status"] == "healthy"
    assert abs(health["memory_mb"] - current_mb) < 5.0


def test_memory_monitor_triggers_gc_on_threshold():
    """Verify MemoryMonitor triggers garbage collection when threshold is exceeded."""
    # Set artificial low warning threshold to test GC trigger
    mon = MemoryMonitor(warning_threshold_mb=1.0, critical_threshold_mb=10000.0)
    health = mon.check_memory_health()

    assert health["status"] == "warning"
    assert len(health["actions_taken"]) > 0
    assert "Warning GC triggered" in health["actions_taken"][0]


# ============================================================================
# 2. CRASH RECOVERY & ATOMIC CHECKPOINTING TESTS
# ============================================================================

def test_crash_recovery_checkpoint_lifecycle(tmp_path):
    """Verify CrashRecoveryManager saves atomic checkpoint, recovers it, and clears it."""
    ckpt_file = tmp_path / "checkpoint.json"
    crm = CrashRecoveryManager(checkpoint_path=str(ckpt_file))

    # 1. Save checkpoint
    crm.save_checkpoint(
        task_id="task_crash_99",
        goal="Organize desktop folders",
        steps=[{"step_id": "s1", "status": "completed"}, {"step_id": "s2", "status": "pending"}],
        status="running"
    )
    assert os.path.exists(ckpt_file)

    # 2. Load checkpoint
    loaded = crm.load_checkpoint()
    assert loaded is not None
    assert loaded["task_id"] == "task_crash_99"
    assert len(loaded["steps"]) == 2
    assert loaded["steps"][0]["status"] == "completed"

    # 3. Clear checkpoint
    crm.clear_checkpoint()
    assert os.path.exists(ckpt_file) is False
    assert crm.load_checkpoint() is None


# ============================================================================
# 3. GRACEFUL SHUTDOWN HANDLER TESTS
# ============================================================================

def test_graceful_shutdown_cleanup(tmp_path):
    """Verify GracefulShutdownHandler saves active task checkpoint and releases buttons."""
    ckpt_file = tmp_path / "shutdown_ckpt.json"
    crm = CrashRecoveryManager(checkpoint_path=str(ckpt_file))

    st = StateTracker()
    st.task_id = "task_shutdown_88"
    st.current_task = "Run multi-step report"
    st.update_status("running")
    st.steps = [{"step_id": "step_1", "status": "pending"}]

    res = GracefulShutdownHandler.perform_shutdown_cleanup(
        task_id=st.task_id,
        state_tracker=st,
        recovery_manager=crm
    )

    assert res["buttons_released"] is True
    assert res["checkpoint_saved"] is True
    assert res["status"] == "gracefully_stopped"

    # Verify saved checkpoint has paused_for_shutdown status
    saved = crm.load_checkpoint()
    assert saved["task_id"] == "task_shutdown_88"
    assert saved["status"] == "paused_for_shutdown"


# ============================================================================
# 4. HIGH VOLUME STRESS CHECK
# ============================================================================

def test_high_volume_checkpoint_stress(tmp_path):
    """Verify high volume checkpoint saves and loads remain stable without corruption."""
    ckpt_file = tmp_path / "stress_ckpt.json"
    crm = CrashRecoveryManager(checkpoint_path=str(ckpt_file))

    for i in range(25):
        crm.save_checkpoint(
            task_id=f"task_{i}",
            goal=f"Stress step {i}",
            steps=[{"idx": i}],
            status="running"
        )

    last_ckpt = crm.load_checkpoint()
    assert last_ckpt["task_id"] == "task_24"
    assert last_ckpt["goal"] == "Stress step 24"
