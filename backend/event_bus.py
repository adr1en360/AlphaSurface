"""
AlphaSurface — Event bus for agent coordination.

The bus tracks two independent signals:
  audio_signal   → updated whenever a user audio chunk arrives
  canvas_signal  → updated whenever canvas shape inventory changes

When BOTH have been still for IDLE_THRESHOLD seconds AND the provocation
cooldown has passed → "provocation_ready" fires.

Events published:
  user_speaking      → audio chunk just arrived (was idle before)
  user_silent        → audio went quiet (crossed IDLE_THRESHOLD)
  canvas_changed     → new shapes detected
  canvas_idle        → canvas has been still for IDLE_THRESHOLD seconds
  provocation_ready  → both idle, cooldown cleared — fire a Sarkar challenge
"""

import asyncio
import time
from typing import Callable, Awaitable

IDLE_THRESHOLD = 8.0         # seconds of no activity before idle events fire
PROVOCATION_COOLDOWN = 45.0  # minimum gap between provocation_ready events


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable[[], Awaitable[None]]]] = {}
        self._last_audio: float = time.monotonic()
        self._last_canvas: float = time.monotonic()
        self._last_provocation: float = 0.0
        self._last_agent_action: float = 0.0   # any agent placing any shape
        self._audio_idle = False
        self._canvas_idle = False
        self._provocation_armed = False
        self._monitor_task: asyncio.Task | None = None

    # ── Subscribe / publish ───────────────────────────────────────────────────

    def subscribe(self, event: str, handler: Callable[[], Awaitable[None]]):
        """Register an async handler for an event name."""
        self._handlers.setdefault(event, []).append(handler)

    async def publish(self, event: str):
        """Fire all handlers registered for event. Each runs as its own task."""
        for handler in self._handlers.get(event, []):
            asyncio.create_task(handler())

    # ── Signal methods (called by main.py / agent.py) ─────────────────────────

    def signal_audio(self):
        """Call this every time a user audio chunk arrives."""
        was_idle = self._audio_idle
        self._last_audio = time.monotonic()
        self._provocation_armed = True
        if self._audio_idle:
            self._audio_idle = False
        if was_idle:
            asyncio.create_task(self.publish("user_speaking"))

    def signal_canvas_change(self):
        """Call when canvas shape inventory changes (new/deleted shapes)."""
        self._last_canvas = time.monotonic()
        self._canvas_idle = False
        self._provocation_armed = True
        asyncio.create_task(self.publish("canvas_changed"))

    def signal_provocation_placed(self):
        """Call after a provocation note lands on canvas — resets cooldown."""
        now = time.monotonic()
        self._last_provocation = now
        self._last_agent_action = now
        self._provocation_armed = False

    def signal_agent_acted(self):
        """
        Call whenever ANY agent places shapes on the canvas.
        Prevents two agents from acting simultaneously on the same idle trigger.
        ResearchAgent, YouTubeAgent, ImageGenAgent — all call this after placing.
        """
        self._last_agent_action = time.monotonic()

    def is_agent_cooldown_active(self, cooldown: float = 8.0) -> bool:
        """
        Returns True if an agent has acted within the last `cooldown` seconds.
        Action agents check this before placing shapes — if True, they stand down.
        B-risk mitigation: prevents two agents overlapping on the same idle trigger.
        """
        return (time.monotonic() - self._last_agent_action) < cooldown

    # ── Background monitor ────────────────────────────────────────────────────

    def start(self):
        """Start the idle monitor. Call once at app startup."""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._idle_monitor())

    def reset_timers(self):
        """Reset idle timers — call when a new Live session starts."""
        now = time.monotonic()
        self._last_audio = now
        self._last_canvas = now
        self._audio_idle = False
        self._canvas_idle = False
        self._provocation_armed = False

    def stop(self):
        if self._monitor_task:
            self._monitor_task.cancel()

    async def _idle_monitor(self):
        """Polls every second. Fires idle + provocation_ready events."""
        while True:
            try:
                await asyncio.sleep(1.0)
                now = time.monotonic()

                # ── Canvas idle ────────────────────────────────────────────
                if not self._canvas_idle and (now - self._last_canvas) >= IDLE_THRESHOLD:
                    self._canvas_idle = True
                    await self.publish("canvas_idle")

                # ── Audio idle ─────────────────────────────────────────────
                if not self._audio_idle and (now - self._last_audio) >= IDLE_THRESHOLD:
                    self._audio_idle = True
                    await self.publish("user_silent")

                # ── Provocation ready ──────────────────────────────────────
                # Only when BOTH signals idle AND provocation cooldown cleared
                # AND no other agent has acted recently (B-risk mitigation).
                if (
                    self._canvas_idle
                    and self._audio_idle
                    and self._provocation_armed
                    and (now - self._last_provocation) >= PROVOCATION_COOLDOWN
                    and not self.is_agent_cooldown_active(cooldown=5.0)
                ):
                    self._last_provocation = now  # prevent double-fire
                    self._provocation_armed = False
                    await self.publish("provocation_ready")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[EventBus] Monitor error: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
