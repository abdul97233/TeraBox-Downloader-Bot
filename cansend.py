import asyncio
import time


class CanSend:
    __slots__ = ("interval", "_last_send")

    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self._last_send = 0.0

    def can_send(self) -> bool:
        now = time.monotonic()
        if now - self._last_send < self.interval:
            return False
        self._last_send = now
        return True

    async def wait(self) -> None:
        now = time.monotonic()
        remaining = self.interval - (now - self._last_send)
        if remaining > 0:
            await asyncio.sleep(remaining)
        self._last_send = time.monotonic()
