import asyncio
from enum import Enum

class ControlState(str, Enum):
    AI_CONTROL = "AI_CONTROL"
    HUMAN_CONTROL = "HUMAN_CONTROL"
    TRANSITIONING = "TRANSITIONING"

class TakeoverManager:
    def __init__(self):
        self._control_state = ControlState.AI_CONTROL
        self._resume_event = asyncio.Event()
        self._resume_event.set()  # default running

    @property
    def control_state(self) -> ControlState:
        return self._control_state

    @property
    def is_takeover_active(self) -> bool:
        return self._control_state == ControlState.HUMAN_CONTROL

    def take_control(self) -> bool:
        """
        Transition control ownership to HUMAN_CONTROL.
        Can only transition from AI_CONTROL.
        """
        if self._control_state == ControlState.HUMAN_CONTROL:
            return True  # Idempotent return for already human control
        if self._control_state != ControlState.AI_CONTROL:
            return False  # Reject other state transitions
            
        self._control_state = ControlState.TRANSITIONING
        self._resume_event.clear()
        self._control_state = ControlState.HUMAN_CONTROL
        return True

    def release_control(self) -> bool:
        """
        Transition control ownership back to AI_CONTROL.
        Can only transition from HUMAN_CONTROL.
        """
        if self._control_state == ControlState.AI_CONTROL:
            return True  # Idempotent return for already AI control
        if self._control_state != ControlState.HUMAN_CONTROL:
            return False  # Reject other state transitions
            
        self._control_state = ControlState.TRANSITIONING
        self._resume_event.set()
        self._control_state = ControlState.AI_CONTROL
        return True

    async def wait_if_takeover(self):
        """Blocks execution if human takeover is active, until control is released."""
        if self.is_takeover_active:
            await self._resume_event.wait()
