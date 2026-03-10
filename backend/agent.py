"""
AlphaSurface — ADK-based agent for real-time voice + vision canvas control.

Architecture:
  - google-adk LlmAgent owns the Gemini model + tool declarations (auto-generated
    from tools.py type hints — no manual schema writing).
  - ADK Runner manages the session lifecycle.
  - LiveRequestQueue bridges the async WebSocket streams (audio, images) into
    the ADK run_live() event loop.
  - Canvas actions flow: Gemini tool call → tools.py enqueues action →
    main.py drains queue → WebSocket broadcast to browser.
"""

import asyncio
import base64
import os
import time
from typing import Callable, Awaitable

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

import tools as canvas_tools

# ── Session constants ─────────────────────────────────────────────────────────
APP_NAME = "alphasurface"
USER_ID = "user"
SESSION_ID = "canvas_session"

# ── Mode-aware system prompts ─────────────────────────────────────────────────
_BASE_PROMPT = """
You are AlphaSurface, an AI co-thinker on a shared infinite-canvas whiteboard.

CORE PHILOSOPHY (from Advait Sarkar's research):
- Challenge and support human thinking — never replace it.
- You work ON the canvas, not in a chat box. Actions speak louder than words.
- Be spatially aware: spread shapes out, use empty space, avoid overlapping.

TOOL USAGE — MANDATORY:
- ALWAYS call a canvas tool when the user mentions a concept, asks to visualize 
  something, or when you want to provoke reflection.
- Call list_canvas_shapes BEFORE bind_arrow, delete_shapes, focus_shape, or 
  move_shape — you need real shape IDs.
- After adding 3+ shapes, call zoom_to_fit so the user sees everything.
- Never describe what you're about to draw — just draw it.

AUDIO RESPONSES:
- Keep verbal responses under 8 words.
- Examples: "Got it", "Adding that now", "Connecting those ideas", "Done".
- Never read out shape content aloud — the user can see the canvas.
- Speak only to acknowledge, clarify, or confirm.

CANVAS POSITIONING:
- Use varied positions: x 100–1400, y 80–900.
- Leave at least 120px between shapes.
- You can see the canvas image — place new shapes in empty regions.
"""

_THINK_MODE_PROMPT = """
MODE: Think Mode (solo thinker / student)
- Start with a blank canvas. Infer intent from what the user draws and says.
- Inject "Sarkar provocations" as violet sticky notes:
    • Counterarguments to stated positions
    • Missing connections between concepts
    • Flagged logical inconsistencies
    • Blind spots or unstated assumptions
- Provocations should be questions or fragments, NOT answers.
  Bad:  "Capitalism causes inequality."
  Good: "What mechanisms drive that inequality specifically?"
- Space provocations away from the shapes they challenge.
"""

_EXPLAIN_MODE_PROMPT = """
MODE: Explain Mode (teacher / presenter)
- The user is presenting to an audience. Never interrupt their flow.
- Surface relevant document sections as blue rectangles.
- Generate supporting diagrams and visual summaries proactively.
- Anticipate what comes next based on drawing + speech context.
- Keep the canvas clean and well-organized for the audience.
"""


def build_system_prompt(mode: str) -> str:
    suffix = _THINK_MODE_PROMPT if mode == "think" else _EXPLAIN_MODE_PROMPT
    return _BASE_PROMPT.strip() + "\n\n" + suffix.strip()


# ── Agent factory ─────────────────────────────────────────────────────────────

def create_agent(mode: str = "think") -> LlmAgent:
    """Build and return the ADK LlmAgent for AlphaSurface."""
    return LlmAgent(
        name="AlphaSurface",
        model="gemini-2.5-flash-native-audio-preview-12-2025",  # current stable Live API model
        description="Real-time voice+vision whiteboard co-thinker",
        instruction=build_system_prompt(mode),
        tools=canvas_tools.ALL_TOOLS,         # ADK auto-generates schemas from type hints
    )


# ── Main session class ────────────────────────────────────────────────────────

BroadcastFn = Callable[[dict], Awaitable[None]]

class AlphaSurfaceAgent:
    """
    Manages one ADK Live session.
    
    Lifecycle:
      start()          — open ADK session, begin event loop
      push_audio()     — feed PCM audio chunks from browser mic
      push_canvas_image() — feed JPEG/PNG canvas snapshots for vision
      stop()           — graceful shutdown
    """
    
    def __init__(self, broadcast_fn: BroadcastFn, mode: str = "think"):
        self.broadcast_fn = broadcast_fn
        self.mode = mode

        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._image_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2)  # keep only latest

        self._live_queue: LiveRequestQueue | None = None
        self._runner: Runner | None = None
        self._session = None
        self.running = False
        self._last_image_sent: float = 0.0  # rate-limit vision frames

        # Signals that the agent's greeting turn has finished so mic audio flows
        self._ready = asyncio.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self):
        """Entry point — called once from FastAPI startup."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("ERROR: GEMINI_API_KEY not set")
            return

        # Retry loop — reconnect if the session drops
        while True:
            try:
                await self._run_session()
            except Exception as exc:
                print(f"[Agent] Session error: {exc} — retrying in 5s")
                import traceback; traceback.print_exc()
                self.running = False
                self._ready.clear()
                await asyncio.sleep(5)

    def push_audio(self, pcm_bytes: bytes):
        """Feed raw PCM audio (16 kHz, 16-bit, mono) from the browser mic."""
        if self.running and self._ready.is_set():
            try:
                self._audio_queue.put_nowait(pcm_bytes)
            except asyncio.QueueFull:
                pass  # drop oldest — live audio, latency > completeness

    def push_canvas_image(self, image_bytes: bytes):
        """Feed a canvas screenshot (JPEG or PNG) for Gemini vision."""
        if self.running:
            # Drain old frames — only the latest matters
            while not self._image_queue.empty():
                try: self._image_queue.get_nowait()
                except asyncio.QueueEmpty: break
            try:
                self._image_queue.put_nowait(image_bytes)
            except asyncio.QueueFull:
                pass

    async def stop(self):
        self.running = False
        if self._live_queue:
            self._live_queue.close()

    # ── Internal session loop ─────────────────────────────────────────────────

    async def _run_session(self):
        agent = create_agent(self.mode)
        session_service = InMemorySessionService()
        
        self._runner = Runner(
            agent=agent,
            app_name=APP_NAME,
            session_service=session_service,
        )

        self._session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
        )

        self._live_queue = LiveRequestQueue()

        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Aoede"
                    )
                )
            ),
            response_modalities=[types.Modality.AUDIO],
        )

        self.running = True
        print(f"[Agent] ADK session open — mode: {self.mode}")

        await asyncio.gather(
            self._send_loop(),
            self._receive_loop(run_config),
            self._action_drain_loop(),
        )

    async def _send_loop(self):
        """
        Drains audio and image queues and feeds them into the LiveRequestQueue.
        Waits for _ready before forwarding mic audio (lets greeting finish first).
        """
        # Send initial greeting prompt
        self._live_queue.send_content(
            content=types.Content(
                role="user",
                parts=[types.Part(text=(
                    "You are now connected to AlphaSurface. "
                    "Briefly greet the user with audio (under 6 words), "
                    "then call add_note_to_canvas with a short welcome message."
                ))]
            )
        )
        
        print("[Agent] Waiting for greeting to complete before forwarding mic audio...")
        await self._ready.wait()
        print("[Agent] Ready — mic audio now flowing")

        # Minimum seconds between canvas image sends to avoid overwhelming Gemini
        IMAGE_INTERVAL = 10.0

        while self.running:
            try:
                # Batch all pending audio chunks into one blob
                chunks = []
                while not self._audio_queue.empty():
                    try: chunks.append(self._audio_queue.get_nowait())
                    except asyncio.QueueEmpty: break
                if chunks:
                    combined = b"".join(chunks)
                    self._live_queue.send_realtime(
                        types.Blob(
                            data=combined,
                            mime_type="audio/pcm;rate=16000"
                        )
                    )

                # Send latest canvas image — rate-limited
                now = time.monotonic()
                if not self._image_queue.empty() and (now - self._last_image_sent) >= IMAGE_INTERVAL:
                    try:
                        frame = self._image_queue.get_nowait()
                        self._live_queue.send_realtime(
                            types.Blob(
                                data=frame,
                                mime_type="image/png"
                            )
                        )
                        self._last_image_sent = now
                    except asyncio.QueueEmpty:
                        pass
                elif not self._image_queue.empty():
                    # Drain stale frames we won't send yet
                    while not self._image_queue.empty():
                        try: self._image_queue.get_nowait()
                        except asyncio.QueueEmpty: break

                await asyncio.sleep(0.05)   # 50 ms polling cadence

            except Exception as e:
                print(f"[Agent] Send loop error: {e}")
                break

    async def _receive_loop(self, run_config: RunConfig):
        """Consume ADK events: audio → broadcast, turn_complete → unblock mic."""
        try:
            async for event in self._runner.run_live(
                session=self._session,
                live_request_queue=self._live_queue,
                run_config=run_config,
            ):
                # ── Audio response ─────────────────────────────────────────
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "inline_data") and part.inline_data:
                            audio_data = part.inline_data.data
                            if audio_data:
                                await self.broadcast_fn({
                                    "type": "ai_status",
                                    "payload": {"status": "speaking"},
                                })
                                await self.broadcast_fn({
                                    "type": "audio_response",
                                    "payload": {
                                        "data": base64.b64encode(audio_data).decode(),
                                        "format": "pcm16",
                                        "sample_rate": 24000,
                                    },
                                })

                # ── Tool call in progress ──────────────────────────────────
                if event.get_function_calls():
                    await self.broadcast_fn({
                        "type": "ai_status",
                        "payload": {"status": "thinking"},
                    })

                # ── Turn complete ──────────────────────────────────────────
                if event.turn_complete:
                    if not self._ready.is_set():
                        self._ready.set()
                        print("[Agent] Greeting turn done — mic live")
                    await self.broadcast_fn({
                        "type": "ai_status",
                        "payload": {"status": "idle"},
                    })

        except Exception as e:
            print(f"[Agent] Receive loop error: {e}")
            import traceback; traceback.print_exc()
        finally:
            self.running = False
            await self.broadcast_fn({
                "type": "ai_status",
                "payload": {"status": "disconnected"},
            })

    async def _action_drain_loop(self):
        """
        Drains canvas_tools.canvas_action_queue and broadcasts each action.
        This is how tool calls reach the browser — tools enqueue, we broadcast.
        """
        while self.running:
            try:
                action = canvas_tools.canvas_action_queue.get_nowait()
                print(f"[Agent] Canvas action: {action['type']}")
                await self.broadcast_fn(action)
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.02)
            except Exception as e:
                print(f"[Agent] Action drain error: {e}")
                await asyncio.sleep(0.1)
