"""
AlphaSurface — ADK-based agent for real-time voice + vision canvas control.

Key changes from v1:
  - Proactive vision: when a canvas image arrives, a soft text nudge is sent
    alongside it so Gemini can act on what it SEES, not just what it hears.
  - Interruption: event.interrupted → broadcast ai_interrupted → frontend
    flushes audio playback queue immediately (barge-in works).
  - System prompt completely rewritten:
      • Only available tools documented
      • Sarkar provocations are genuine open questions, never conclusions
      • Spatial overlap prevention with explicit rules
      • Non-intrusive philosophy enforced
  - Config: accepts web_search flag from launch UI
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

APP_NAME = "alphasurface"
USER_ID = "user"
SESSION_ID = "canvas_session"

# ── System prompts ────────────────────────────────────────────────────────────

_BASE_PROMPT = """
You are AlphaSurface — a silent, spatial AI co-thinker on a shared infinite canvas.

═══════════════════════════════════════════════════════
CORE PHILOSOPHY 
═══════════════════════════════════════════════════════
You work ALONGSIDE the human, never INSTEAD of them.
You challenge and support thinking — you do NOT compete with the process.
The canvas is THEIRS. You are a guest on it.
You are NON-INTRUSIVE: one action at a time, spaced out, unannounced.

═══════════════════════════════════════════════════════
WHAT YOU CAN SEE
═══════════════════════════════════════════════════════
You receive:
  1. A live canvas screenshot (image) every ~10 seconds
  2. Continuous microphone audio from the user
  3. Shape inventory via list_canvas_shapes (call before any edit)

When you receive a canvas image, look carefully:
  - What has the user drawn? (shapes, freehand sketches, text, arrows)
  - Are there freehand marker strokes? Treat them as meaningful — they show thinking.
  - Is there something unconnected that could benefit from a link?
  - Are there claims that lack evidence or could be challenged?
  - Is there dead space you could use for a provocation?

═══════════════════════════════════════════════════════
AVAILABLE TOOLS  (only call tools in this list)
═══════════════════════════════════════════════════════
WRITE:    add_text_to_canvas, add_note_to_canvas, add_geo_to_canvas,
          add_arrow_to_canvas, bind_arrow
EMBED:    add_embed_to_canvas (YouTube/Figma/Maps live iframe),
          add_bookmark_to_canvas (rich link card)
EDIT:     move_shape, update_shape, delete_shapes
NAVIGATE: zoom_to_fit, focus_shape, select_shapes, clear_canvas
READ:     list_canvas_shapes ← ALWAYS call before any edit/bind/delete

DO NOT call: add_image, add_draw, add_frame, group_shapes,
             ungroup_shapes, resize_shape, reorder_shape,
             set_camera, process_information
These do not exist — calling them will silently fail.

═══════════════════════════════════════════════════════
SPATIAL RULES  (overlap prevention)
═══════════════════════════════════════════════════════
1. Call list_canvas_shapes to get current shape positions (x, y, w, h).
2. Never place a shape within 150px of an existing shape's bounding box.
3. Use the full canvas space: x range 80–1500, y range 60–950.
4. Prefer placing shapes in empty quadrants you can see in the screenshot.
5. After placing 3+ shapes, call zoom_to_fit.
6. Do NOT cluster everything in the center.

═══════════════════════════════════════════════════════
AUDIO RULES
═══════════════════════════════════════════════════════
- Verbal responses: MAXIMUM 6 words. ("Done", "Adding now", "Got it", "Connecting those")
- Never read shape content aloud. The user can see the canvas.
- Never explain what you're about to do. Just do it.
- Do not narrate your tool calls.

═══════════════════════════════════════════════════════
FREEHAND SKETCH AWARENESS
═══════════════════════════════════════════════════════
The user may draw with the marker/pencil tool. These appear in the canvas image
as freehand strokes — they will NOT appear in list_canvas_shapes.
You can STILL see them in the screenshot.
When you see freehand drawings:
  - Acknowledge them visually (place a related note nearby)
  - Treat them as ideas in progress, not complete thoughts
  - Do NOT ask the user to explain them — infer from context
"""

_THINK_MODE_PROMPT = """
═══════════════════════════════════════════════════════
MODE: Think Mode  (solo thinker / student)
═══════════════════════════════════════════════════════
The canvas starts blank. The user is developing their own thinking.
Your role: inject quiet provocations — never answers.

PROVOCATION RULES:
  Color: always violet sticky notes
  Placement: near the shape you're provoking, but not overlapping it (150px away)
  Frequency: maximum 1 provocation per 30 seconds of quiet
  Trigger: place a provocation when you notice:
    - A concept with no connection to anything else
    - A claim presented as fact with no evidence nearby
    - Two ideas that seem to contradict each other
    - An assumption so obvious the user hasn't questioned it

PROVOCATION FORMAT — OPEN QUESTIONS ONLY:
  ✅ GOOD (open, specific, genuinely uncertain):
    "What breaks this if X changes?"
    "Who benefits from the opposite view?"
    "What would falsify this?"
    "What's the simplest case where this fails?"
    "What does 'better' mean here exactly?"

  ❌ BAD (conclusions, statements, answers):
    "This assumes capitalism causes inequality."
    "Consider the systemic factors."
    "This lacks evidence."
    "You should think about X."

PROACTIVE VISION:
  When you receive a canvas image and the user has been quiet for 10+ seconds:
  - Scan for the above triggers
  - If you find one, place a single violet provocation
  - No audio. No narration. Just the note.
  - Then wait. Do not cascade with more.
"""

_EXPLAIN_MODE_PROMPT = """
═══════════════════════════════════════════════════════
MODE: Explain Mode  (teacher / presenter)
═══════════════════════════════════════════════════════
The user is presenting to an audience. Your job is to SUPPORT, not interrupt.

RULES:
  - Never act during mid-sentence — wait for natural pauses
  - Surface relevant concepts as blue geo shapes near what's being drawn
  - Use add_embed_to_canvas for YouTube when a topic benefits from video
  - Use add_bookmark_to_canvas for reference links
  - Anticipate: if they just drew "photosynthesis", prepare a related concept
  - Keep the canvas organized — new shapes go in clean empty areas

WHEN TO ACT:
  - User mentions a concept → place a supporting definition nearby
  - User asks a rhetorical question → place the answer as a geo shape
  - User references an external resource → place a bookmark
  - Canvas gets crowded → call zoom_to_fit

NEVER:
  - Place a shape that contradicts what the presenter just said
  - Add provocations (that's Think Mode)
  - Interrupt mid-explanation
"""


def build_system_prompt(mode: str, web_search: bool = False) -> str:
    suffix = _THINK_MODE_PROMPT if mode == "think" else _EXPLAIN_MODE_PROMPT
    prompt = _BASE_PROMPT.strip() + "\n\n" + suffix.strip()
    if web_search:
        prompt += """

═══════════════════════════════════════════════════════
WEB SEARCH
═══════════════════════════════════════════════════════
You have web search enabled. When the user asks about a real-world fact,
recent event, or resource you don't know, search for it and place a
bookmark on the canvas with the best result URL.
Do NOT search for things you already know.
"""
    return prompt


def create_agent(mode: str = "think", web_search: bool = False) -> LlmAgent:
    return LlmAgent(
        name="AlphaSurface",
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        description="Real-time voice+vision whiteboard co-thinker",
        instruction=build_system_prompt(mode, web_search),
        tools=canvas_tools.ALL_TOOLS,
    )


# ── Session class ─────────────────────────────────────────────────────────────

BroadcastFn = Callable[[dict], Awaitable[None]]


class AlphaSurfaceAgent:
    def __init__(self, broadcast_fn: BroadcastFn, mode: str = "think", web_search: bool = False):
        self.broadcast_fn = broadcast_fn
        self.mode = mode
        self.web_search = web_search

        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._image_queue: asyncio.Queue[tuple[bytes, str]] = asyncio.Queue(maxsize=2)

        self._live_queue: LiveRequestQueue | None = None
        self._runner: Runner | None = None
        self._session = None
        self.running = False
        self._last_image_sent: float = 0.0
        self._last_image_nudge: float = 0.0  # rate-limit proactive nudges
        self._ready = asyncio.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("ERROR: GEMINI_API_KEY not set")
            return
        while True:
            try:
                await self._run_session()
            except Exception as exc:
                print(f"[Agent] Session error: {exc} — retrying in 5s")
                import traceback; traceback.print_exc()
                self.running = False
                self._ready.clear()
                await asyncio.sleep(5)

    def reconfigure(self, mode: str = None, web_search: bool = None):
        """Update mode/web_search — takes effect on next session restart."""
        if mode is not None:
            self.mode = mode
        if web_search is not None:
            self.web_search = web_search

    def push_audio(self, pcm_bytes: bytes):
        if self.running and self._ready.is_set():
            try:
                self._audio_queue.put_nowait(pcm_bytes)
            except asyncio.QueueFull:
                pass

    def push_canvas_image(self, image_bytes: bytes, mime: str = "image/png"):
        if self.running:
            while not self._image_queue.empty():
                try: self._image_queue.get_nowait()
                except asyncio.QueueEmpty: break
            try:
                self._image_queue.put_nowait((image_bytes, mime))
            except asyncio.QueueFull:
                pass

    async def stop(self):
        self.running = False
        if self._live_queue:
            self._live_queue.close()

    # ── Session lifecycle ─────────────────────────────────────────────────────

    async def _run_session(self):
        agent = create_agent(self.mode, self.web_search)
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
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            response_modalities=[types.Modality.AUDIO],
        )

        self.running = True
        print(f"[Agent] Session open — mode={self.mode} web_search={self.web_search}")

        await asyncio.gather(
            self._send_loop(),
            self._receive_loop(run_config),
            self._action_drain_loop(),
        )

    async def _send_loop(self):
        """Feed audio + canvas images into the LiveRequestQueue."""
        # Initial greeting
        self._live_queue.send_content(
            content=types.Content(
                role="user",
                parts=[types.Part(text=(
                    "AlphaSurface is now connected. "
                    "Greet the user in under 5 words (audio only), "
                    "then place one welcome sticky note on the canvas."
                ))]
            )
        )

        print("[Agent] Waiting for greeting…")
        await self._ready.wait()
        print("[Agent] Ready — mic live")

        IMAGE_INTERVAL = 20.0   # seconds between canvas image sends to Gemini
        NUDGE_INTERVAL = 30.0   # seconds between proactive vision nudges

        while self.running:
            try:
                # ── Audio ──────────────────────────────────────────────────
                chunks = []
                while not self._audio_queue.empty():
                    try: chunks.append(self._audio_queue.get_nowait())
                    except asyncio.QueueEmpty: break
                if chunks:
                    self._live_queue.send_realtime(
                        types.Blob(data=b"".join(chunks), mime_type="audio/pcm;rate=16000")
                    )

                # ── Canvas image + proactive nudge ─────────────────────────
                now = time.monotonic()
                if not self._image_queue.empty() and (now - self._last_image_sent) >= IMAGE_INTERVAL:
                    try:
                        frame, frame_mime = self._image_queue.get_nowait()

                        # Decide whether to include a proactive vision nudge.
                        # This makes the agent act on what it SEES, not just hears.
                        should_nudge = (now - self._last_image_nudge) >= NUDGE_INTERVAL

                        if should_nudge:
                            # Send image + text together so Gemini analyzes both
                            self._live_queue.send_content(
                                content=types.Content(
                                    role="user",
                                    parts=[
                                        types.Part(
                                            inline_data=types.Blob(data=frame, mime_type=frame_mime)
                                        ),
                                        types.Part(text=(
                                            "Canvas updated. Look carefully at what you see — "
                                            "including any freehand sketches or marker strokes. "
                                            "If you notice an unconnected idea, a missing link, "
                                            "or a provocation opportunity, act on it silently. "
                                            "If nothing stands out, do nothing."
                                        ))
                                    ]
                                )
                            )
                            self._last_image_nudge = now
                        else:
                            # Send image only (vision context update, no trigger)
                            self._live_queue.send_realtime(
                                types.Blob(data=frame, mime_type=frame_mime)
                            )

                        self._last_image_sent = now
                    except asyncio.QueueEmpty:
                        pass
                elif not self._image_queue.empty():
                    # Drain stale frames
                    while not self._image_queue.empty():
                        try: self._image_queue.get_nowait()
                        except asyncio.QueueEmpty: break

                await asyncio.sleep(0.05)

            except Exception as e:
                print(f"[Agent] Send loop error: {e}")
                break

    async def _receive_loop(self, run_config: RunConfig):
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
                                await self.broadcast_fn({"type": "ai_status", "payload": {"status": "speaking"}})
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
                    await self.broadcast_fn({"type": "ai_status", "payload": {"status": "thinking"}})

                # ── Barge-in interrupt ─────────────────────────────────────
                # Fires when Gemini VAD detects user speech during AI output.
                # Frontend must flush its audio playback queue.
                # Requires echoCancellation:true in browser getUserMedia().
                if getattr(event, "interrupted", False):
                    print("[Agent] Barge-in — flushing frontend audio")
                    await self.broadcast_fn({"type": "ai_interrupted", "payload": {}})
                    await self.broadcast_fn({"type": "ai_status", "payload": {"status": "idle"}})

                # ── Turn complete ──────────────────────────────────────────
                if event.turn_complete:
                    if not self._ready.is_set():
                        self._ready.set()
                        print("[Agent] Greeting done — mic live")
                    await self.broadcast_fn({"type": "ai_status", "payload": {"status": "idle"}})

        except Exception as e:
            print(f"[Agent] Receive loop error: {e}")
            import traceback; traceback.print_exc()
        finally:
            self.running = False
            await self.broadcast_fn({"type": "ai_status", "payload": {"status": "disconnected"}})

    async def _action_drain_loop(self):
        """Drain canvas_tools.canvas_action_queue → broadcast to browser."""
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
