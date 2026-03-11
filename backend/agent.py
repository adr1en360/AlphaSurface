"""
AlphaSurface — ADK Live agent (v2).

Changes from v1:
  ✅ reconfigure() now RESTARTS the session (closes queue → retry loop fires)
  ✅ web_search routes through ResearchAgent (Live API rejects native google_search)
  ✅ Silence detection is event-driven via EventBus (not timer polling)
      — provocation fires when BOTH audio AND canvas have been idle 8s+
      — never fires while user is speaking or drawing
  ✅ Persona context injected into system prompt at session start
  ✅ No welcome sticky note — greeting is audio only, ≤5 words
  ✅ PersonaAgent updates memory continuously via event bus subscription
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
from event_bus import get_event_bus
from memory import memory_store

# NOTE: google_search ADK tool is NOT attached to the Live Agent.
# The native audio preview model rejects it with 1008 (policy violation).
# Web search is handled by ResearchAgent via dispatch_research() instead.

APP_NAME = "alphasurface"
USER_ID = "user"
SESSION_ID = "canvas_session"


# ── System prompts ─────────────────────────────────────────────────────────────

_BASE_PROMPT = """
You are AlphaSurface — a silent, spatial AI co-thinker on a shared infinite canvas.

═══════════════════════════════════════════════════════
CORE PHILOSOPHY
═══════════════════════════════════════════════════════
You work ALONGSIDE the human, never INSTEAD of them.
The canvas is THEIRS. You are a guest on it.
NON-INTRUSIVE: one action at a time, spaced out, unannounced.

═══════════════════════════════════════════════════════
WHAT YOU CAN SEE
═══════════════════════════════════════════════════════
You receive:
  1. A live canvas screenshot (image) every ~20 seconds
  2. Continuous microphone audio from the user
  3. Shape inventory via list_canvas_shapes (call before any edit)
  4. Text content via scan_canvas_text (faster than list_canvas_shapes)

When you receive a canvas image:
  - What has the user drawn? (shapes, freehand sketches, text, arrows)
  - Freehand marker strokes appear in the IMAGE but NOT in list_canvas_shapes
  - Treat freehand strokes as thinking in progress — do not ask the user to explain

═══════════════════════════════════════════════════════
AVAILABLE TOOLS  (only call tools in this list)
═══════════════════════════════════════════════════════
READ:     list_canvas_shapes, scan_canvas_text
MEMORY:   memory_read, memory_write
WRITE:    add_text_to_canvas, add_note_to_canvas, add_geo_to_canvas,
          add_arrow_to_canvas, bind_arrow
EMBED:    add_embed_to_canvas, add_bookmark_to_canvas
EDIT:     move_shape, update_shape, delete_shapes
NAVIGATE: zoom_to_fit, focus_shape, select_shapes, clear_canvas
DISPATCH: dispatch_research, dispatch_image_gen

DO NOT call any tool not in this list — it will silently fail.

═══════════════════════════════════════════════════════
MEMORY USAGE
═══════════════════════════════════════════════════════
- At session start: call memory_read("user") to get the user's profile
- Whenever you notice something about how the user thinks or communicates:
  call memory_write("user", key, value) silently
- Examples of things worth remembering:
    "prefers diagrams over text"
    "works on SaaS product problems"
    "responds well to specific questions"
    "dislikes verbose answers"
    "domain: fintech startup"
- Do NOT write memory for every canvas action — only genuine new insights

═══════════════════════════════════════════════════════
SPATIAL RULES  (overlap prevention)
═══════════════════════════════════════════════════════
1. Call list_canvas_shapes before bind_arrow, move, delete, focus.
2. Never place a shape within 150px of an existing shape's bounding box.
3. Canvas space: x range 80–1500, y range 60–950.
4. After placing 3+ shapes, call zoom_to_fit.
5. Do NOT cluster everything in the center.

═══════════════════════════════════════════════════════
AUDIO RULES
═══════════════════════════════════════════════════════
- Verbal responses: MAXIMUM 6 words. ("Done", "Adding now", "Got it")
- Never read shape content aloud. The user can see the canvas.
- Never explain what you're about to do. Just do it.
- Do not narrate your tool calls.
"""

_THINK_MODE_PROMPT = """
═══════════════════════════════════════════════════════
MODE: Think Mode  (solo thinker / student)
═══════════════════════════════════════════════════════
The canvas starts blank. The user is developing their own thinking.
Your role: inject quiet provocations — never answers.

WHEN TO PLACE A PROVOCATION:
  A provocation fires ONLY after:
    1. The user has stopped talking (≥8 seconds of silence)
    2. The canvas has stopped changing (≥8 seconds of no new shapes)
  If the user is mid-sentence or mid-stroke: DO NOTHING.
  Wait for the natural pause. That pause is the provocation window.

PROVOCATION RULES:
  Color: always violet sticky notes
  Placement: near the shape you're provoking, 150px+ away, not overlapping
  Frequency: ONE provocation per quiet window — never cascade
  After placing: call memory_write to record what kind of provocation landed

PROVOCATION FORMAT — OPEN QUESTIONS ONLY:
  ✅ GOOD:
    "What breaks this if X changes?"
    "Who benefits from the opposite view?"
    "What would falsify this?"
    "What's the simplest case where this fails?"
    "What does 'better' mean here exactly?"

  ❌ BAD (never do these):
    "This assumes X."     ← statement, not question
    "Consider Y."         ← directive
    "This lacks evidence." ← verdict
    "You should think about Z." ← suggestion
"""

_PRESENT_MODE_PROMPT = """
═══════════════════════════════════════════════════════
MODE: Present Mode  (teacher / presenter)
═══════════════════════════════════════════════════════
The user is presenting to an audience. Support, never interrupt.

RULES:
  - Never act during mid-sentence — wait for natural pauses
  - Surface relevant concepts as blue geo shapes near what's being drawn
  - Use add_embed_to_canvas for YouTube when a topic benefits from video
  - Use add_bookmark_to_canvas for reference links
  - Keep canvas organised — new shapes go in clean empty areas

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


def _persona_section(persona: dict) -> str:
    """Build a system prompt section from stored persona data."""
    if not persona:
        return ""
    lines = ["═══════════════════════════════════════════════════════",
             "USER PROFILE  (from memory — adapt your behaviour accordingly)",
             "═══════════════════════════════════════════════════════"]
    for k, v in persona.items():
        if k.startswith("_"):
            continue
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def build_system_prompt(mode: str, web_search: bool = False, persona: dict | None = None) -> str:
    suffix = _THINK_MODE_PROMPT if mode == "think" else _PRESENT_MODE_PROMPT
    prompt = _BASE_PROMPT.strip() + "\n\n" + suffix.strip()

    if persona:
        prompt += "\n\n" + _persona_section(persona)

    if web_search:
        prompt += """

═══════════════════════════════════════════════════════
WEB SEARCH (via ResearchAgent)
═══════════════════════════════════════════════════════
When the user asks about a real-world fact, recent event, or wants information
placed on canvas — call dispatch_research("your query") immediately.
ResearchAgent will search the web and place a clean result cluster on canvas.
Do NOT try to answer from memory for factual/current queries.
Do NOT use any other search tool — only dispatch_research.
"""

    prompt += """

═══════════════════════════════════════════════════════
IMAGE GENERATION (via ImageGenAgent)
═══════════════════════════════════════════════════════
When the user asks you to generate, create, or draw an image — call
dispatch_image_gen("detailed description of the image") immediately.
ImageGenAgent will generate the image and place it on canvas.
Do NOT try to describe images in text — generate them.
"""
    return prompt


def create_agent(mode: str = "think", web_search: bool = False, persona: dict | None = None) -> LlmAgent:
    tools = list(canvas_tools.ALL_TOOLS)
    return LlmAgent(
        name="AlphaSurface",
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        description="Real-time voice+vision whiteboard co-thinker",
        instruction=build_system_prompt(mode, web_search, persona),
        tools=tools,
    )


# ── Session class ──────────────────────────────────────────────────────────────

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
        self._ready = asyncio.Event()
        self._restart_requested = False  # set by reconfigure() to force restart

        # Subscribe to provocation_ready so we fire on the correct trigger
        bus = get_event_bus()
        bus.subscribe("provocation_ready", self._on_provocation_ready)

    # ── Public API ─────────────────────────────────────────────────────────────

    async def start(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("ERROR: GEMINI_API_KEY not set")
            return
        while True:
            try:
                self._restart_requested = False
                await self._run_session()
            except Exception as exc:
                print(f"[Agent] Session error: {exc} — retrying in 3s")
                import traceback; traceback.print_exc()
            finally:
                self.running = False
                self._ready.clear()
                await asyncio.sleep(3)

    def reconfigure(self, mode: str = None, web_search: bool = None):
        """
        Update mode/web_search.
        Closes the live queue → forces the retry loop to restart with new config.
        Takes effect within ~3 seconds.
        """
        changed = False
        if mode is not None and mode != self.mode:
            self.mode = mode
            changed = True
        if web_search is not None and web_search != self.web_search:
            self.web_search = web_search
            changed = True

        if changed and self._live_queue:
            print(f"[Agent] Reconfiguring → mode={self.mode} web_search={self.web_search} (restarting session)")
            self._restart_requested = True
            self._live_queue.close()  # triggers gather cancellation → retry loop

    def push_audio(self, pcm_bytes: bytes):
        if self.running and self._ready.is_set():
            get_event_bus().signal_audio()  # ← tell event bus user is speaking
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

    # ── Provocation trigger ────────────────────────────────────────────────────

    async def _on_provocation_ready(self):
        """
        Called by EventBus OR dispatcher when BOTH audio AND canvas have been idle 8s+.
        Sends the current canvas image to Gemini with a targeted provocation prompt.
        Only fires in Think Mode.

        Both paths (event bus and Live Agent dispatch_provocation) land here.
        The dispatcher calls this directly — no duplication because signal_agent_acted()
        is set before this runs, which blocks the event bus from re-firing.
        """
        if not self.running or not self._ready.is_set():
            return
        if self.mode != "think":
            return

        # Grab the latest canvas image if available
        if self._image_queue.empty():
            # No image queued — trigger a text-only provocation
            self._live_queue.send_content(
                content=types.Content(
                    role="user",
                    parts=[types.Part(text=(
                        "The user has paused — both voice and canvas are still. "
                        "Call scan_canvas_text now. "
                        "If you find one idea that deserves a genuine open question, "
                        "place a single violet sticky note as a Sarkar provocation. "
                        "If nothing genuinely stands out, do nothing. "
                        "No audio. No explanation."
                    ))]
                )
            )
        else:
            try:
                frame, frame_mime = self._image_queue.get_nowait()
                self._live_queue.send_content(
                    content=types.Content(
                        role="user",
                        parts=[
                            types.Part(inline_data=types.Blob(data=frame, mime_type=frame_mime)),
                            types.Part(text=(
                                "The user has paused — both voice and canvas are still. "
                                "Look carefully at this canvas. "
                                "Find one idea that deserves a genuine open question. "
                                "Place a single violet sticky note — the question only, nothing else. "
                                "If nothing genuinely stands out, do nothing. "
                                "No audio. No explanation."
                            ))
                        ]
                    )
                )
                get_event_bus().signal_provocation_placed()
                print("[Agent] Provocation triggered (event-driven silence)")
            except asyncio.QueueEmpty:
                pass

    # ── Session lifecycle ──────────────────────────────────────────────────────

    async def _run_session(self):
        # Load persona from memory before creating agent
        persona = await memory_store().read(USER_ID)

        agent = create_agent(self.mode, self.web_search, persona)
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
            response_modalities=["AUDIO"],
        )

        self.running = True
        print(f"[Agent] Session open — mode={self.mode} web_search={self.web_search} persona_keys={list(persona.keys())}")

        # Give PersonaAgent a live handle so it can nudge the Live session mid-stream.
        _lq = self._live_queue
        def _nudge(text: str):
            if self.running and _lq:
                try:
                    _lq.send_content(
                        content=types.Content(
                            role="user",
                            parts=[types.Part(text=text)]
                        )
                    )
                except Exception as e:
                    print(f"[Agent] Nudge failed: {e}")

        from sub_agents.persona_agent import get_persona_agent
        get_persona_agent().set_nudge_fn(_nudge)

        await asyncio.gather(
            self._send_loop(),
            self._receive_loop(run_config),
            self._action_drain_loop(),
        )

    async def _send_loop(self):
        """Feed audio + canvas images into the LiveRequestQueue."""
        # No greeting — session opens silently, mic goes live immediately
        self._ready.set()
        print("[Agent] Ready — mic live")

        IMAGE_INTERVAL = 20.0  # seconds between canvas image sends

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

                # ── Canvas image (vision context only — no automatic nudge) ─
                # Provocations are handled by _on_provocation_ready via EventBus.
                now = time.monotonic()
                if not self._image_queue.empty() and (now - self._last_image_sent) >= IMAGE_INTERVAL:
                    try:
                        frame, frame_mime = self._image_queue.get_nowait()
                        self._live_queue.send_realtime(
                            types.Blob(data=frame, mime_type=frame_mime)
                        )
                        self._last_image_sent = now
                    except asyncio.QueueEmpty:
                        pass
                elif not self._image_queue.empty():
                    # Drain stale frames so queue doesn't block
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

                # ── Barge-in ───────────────────────────────────────────────
                if getattr(event, "interrupted", False):
                    print("[Agent] Barge-in — flushing frontend audio")
                    await self.broadcast_fn({"type": "ai_interrupted", "payload": {}})
                    await self.broadcast_fn({"type": "ai_status", "payload": {"status": "idle"}})

                # ── Turn complete ──────────────────────────────────────────
                if event.turn_complete:
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
