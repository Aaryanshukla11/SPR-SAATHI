import os
import gc
import json
import time
import psutil
import datetime
from typing import Dict, Any, List, Optional
import logging

from agent.core import win32_utils

logger = logging.getLogger("agent.core.production_hardening")


class MemoryMonitor:
    """
    Phase 19: Memory Monitoring and Leak Prevention Engine.
    
    Monitors process RSS memory, tracks growth, and performs automatic
    garbage collection and cache eviction when memory exceeds thresholds.
    """

    def __init__(self, warning_threshold_mb: float = 450.0, critical_threshold_mb: float = 800.0):
        self.warning_threshold_mb = warning_threshold_mb
        self.critical_threshold_mb = critical_threshold_mb
        self._process = psutil.Process(os.getpid())

    def get_current_memory_mb(self) -> float:
        """Returns current process RSS memory in MB."""
        try:
            return round(self._process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            return 0.0

    def check_memory_health(self) -> Dict[str, Any]:
        """
        Evaluates memory footprint against thresholds.
        If warning threshold exceeded, automatically triggers garbage collection.
        """
        mem_mb = self.get_current_memory_mb()
        status = "healthy"
        actions_taken = []

        if mem_mb >= self.critical_threshold_mb:
            status = "critical"
            # Emergency GC collection
            collected = gc.collect()
            actions_taken.append(f"Critical GC triggered, collected {collected} objects")
            logger.error(f"[MEMORY CRITICAL] Process memory is {mem_mb} MB (critical threshold: {self.critical_threshold_mb} MB).")
        elif mem_mb >= self.warning_threshold_mb:
            status = "warning"
            collected = gc.collect()
            actions_taken.append(f"Warning GC triggered, collected {collected} objects")
            logger.warning(f"[MEMORY WARNING] Process memory reached {mem_mb} MB (warning threshold: {self.warning_threshold_mb} MB).")

        return {
            "status": status,
            "memory_mb": mem_mb,
            "actions_taken": actions_taken
        }


class CrashRecoveryManager:
    """
    Phase 19: Crash Recovery and Task Persistence Engine.
    
    Persists atomic checkpoints of active tasks to disk so that unexpected
    backend crashes or reboots can recover the active task without losing state.
    """

    def __init__(self, checkpoint_path: Optional[str] = None):
        if checkpoint_path:
            self.checkpoint_path = os.path.abspath(checkpoint_path)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.checkpoint_path = os.path.join(base_dir, "data", "active_checkpoint.json")

    def save_checkpoint(self, task_id: str, goal: str, steps: List[Dict[str, Any]], status: str):
        """Saves active task state atomically to disk."""
        os.makedirs(os.path.dirname(self.checkpoint_path), exist_ok=True)
        checkpoint = {
            "task_id": task_id,
            "goal": goal,
            "status": status,
            "steps": steps,
            "saved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        tmp_file = f"{self.checkpoint_path}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2)
        os.replace(tmp_file, self.checkpoint_path)

    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Loads unfinalized checkpoint if present."""
        if os.path.exists(self.checkpoint_path):
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load checkpoint: {e}")
        return None

    def clear_checkpoint(self):
        """Clears checkpoint when task successfully finishes."""
        if os.path.exists(self.checkpoint_path):
            try:
                os.remove(self.checkpoint_path)
            except Exception:
                pass


class GracefulShutdownHandler:
    """
    Phase 19: Graceful Shutdown System.
    
    Ensures that when the process terminates:
    1. All OS mouse buttons and keys are released
    2. Active checkpoints are recorded
    3. Open resources are flushed
    """

    @staticmethod
    def perform_shutdown_cleanup(
        task_id: Optional[str] = None,
        state_tracker: Optional[Any] = None,
        recovery_manager: Optional[CrashRecoveryManager] = None
    ) -> Dict[str, Any]:
        logger.info("Initiating graceful shutdown cleanup...")

        # 1. Release Win32 input buttons
        win32_utils.release_all_buttons()

        # 2. Checkpoint state if active
        saved_checkpoint = False
        if task_id and state_tracker and recovery_manager:
            if state_tracker.status in ("running", "planning", "waiting_user", "paused"):
                recovery_manager.save_checkpoint(
                    task_id=task_id,
                    goal=state_tracker.current_task or "",
                    steps=state_tracker.steps,
                    status="paused_for_shutdown"
                )
                saved_checkpoint = True

        # 3. Final GC flush
        gc.collect()

        return {
            "buttons_released": True,
            "checkpoint_saved": saved_checkpoint,
            "status": "gracefully_stopped"
        }


# Global instances
MEMORY_MONITOR = MemoryMonitor()
CRASH_RECOVERY = CrashRecoveryManager()
