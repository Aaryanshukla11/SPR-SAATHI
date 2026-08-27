import asyncio

class TakeoverManager:
    def __init__(self):
        self._takeover_active = False
        # Event to wait on when paused due to takeover
        self._resume_event = asyncio.Event()
        self._resume_event.set() # default running

    @property
    def is_takeover_active(self) -> bool:
        return self._takeover_active

    def take_control(self):
        self._takeover_active = True
        self._resume_event.clear()

    def release_control(self):
        self._takeover_active = False
        self._resume_event.set()

    async def wait_if_takeover(self):
        """Blocks execution if human takeover is active, until control is released."""
        if self._takeover_active:
            await self._resume_event.wait()
