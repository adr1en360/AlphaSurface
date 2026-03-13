import asyncio
import base64
import contextlib
import hashlib
import logging
import os
import time
from typing import Awaitable, Callable

from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import create_agent
from event_bus import get_event_bus
from memory import memory_store
from model_config import FAST_MODEL, LIVE_MODEL

# ADK emits repeated non-fatal warnings for default function-parameter values
# when targeting Gemini API. Keep logs readable by suppressing that warning source.
logging.getLogger("google_adk.google.adk.tools._function_parameter_parse_util").setLevel(logging.ERROR)

APP_NAME = "alphasurface"
USER_ID = "user"
SESSION_ID = "canvas_session"

BroadcastFn = Callable[[dict], Awaitable[None]]


class AlphaSurfaceAgent:
    def __init__(self, broadcast_fn: BroadcastFn, mode: str = "think", web_search: bool = False):
        self.broadcast_fn = broadcast_fn
        self.mode = mode
        self.web_search = web_search

        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._image_queue: asyncio.Queue[tuple[bytes, str]] = asyncio.Queue(maxsize=2)
        self._session_service = InMemorySessionService()

        self._live_queue: LiveRequestQueue | None = None
        self._runner: Runner | None = None
        self._session = None
        self._session_task: asyncio.Task | None = None
        self._session_lock = asyncio.Lock()
        self._emit_disconnected_on_exit = True

        self.running = False
        self._muted = False
        self._last_image_sent: float = 0.0
        self._last_canvas_image_hash: str | None = None
        self._pending_vision_trigger = False
        self._last_vision_trigger: float = 0.0
        self._last_tool_call_time: float = 0.0
        self._last_interrupt_emit: float = 0.0
        self._session_started_at: float = 0.0
        self._interrupt_emit_cooldown = 0.35
        self._is_speaking = False
        self._vision_trigger_cooldown = 60.0
        self._agent_quiet_required = 30.0
        self._ready = asyncio.Event()
        self._recoverable_live_disconnect = False
        self._audio_live_enabled = True
        self._active_live_model = LIVE_MODEL
        self._active_session_id = SESSION_ID
        self._use_text_fallback_once = False

        bus = get_event_bus()
        bus.subscribe("provocation_ready", self._on_provocation_ready)

    def _has_live_credentials(self) -> bool:
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            return True
        return (
            os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true"
            and bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
        )

    async def ensure_session(self):
        if self.running and self._session_task and not self._session_task.done():
            return
        await self.start_session()

    async def start_session(self):
        async with self._session_lock:
            if self.running and self._session_task and not self._session_task.done():
                return
            if not self._has_live_credentials():
                print("[Agent] Live session skipped: missing Gemini or Vertex credentials")
                await self.broadcast_fn({"type": "ai_status", "payload": {"status": "disconnected"}})
                return
            self._emit_disconnected_on_exit = True
            self._session_task = asyncio.create_task(self._run_session())

    async def stop_session(self, emit_disconnected: bool = True):
        async with self._session_lock:
            self._emit_disconnected_on_exit = emit_disconnected
            self.running = False
            self._ready.clear()
            if self._live_queue is not None:
                self._live_queue.close()

            task = self._session_task
            self._session_task = None
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            self._live_queue = None
            self._runner = None
            self._session = None
            from sub_agents.persona_agent import get_persona_agent
            get_persona_agent().set_nudge_fn(None)

    async def reconfigure(self, mode: str | None = None, web_search: bool | None = None):
        changed = False
        if mode is not None and mode != self.mode:
            self.mode = mode
            changed = True
        if web_search is not None and web_search != self.web_search:
            self.web_search = web_search
            changed = True

        if changed and (self.running or self._session_task):
            print(f"[Agent] Reconfiguring → mode={self.mode} web_search={self.web_search}")
            await self.stop_session(emit_disconnected=False)

        await self.ensure_session()

    def push_audio(self, pcm_bytes: bytes):
        if self.running and self._ready.is_set():
            get_event_bus().signal_audio()
            try:
                self._audio_queue.put_nowait(pcm_bytes)
            except asyncio.QueueFull:
                pass

    def push_canvas_image(self, image_bytes: bytes, mime: str = "image/png"):
        if not self.running:
            return

        image_hash = hashlib.sha1(image_bytes).hexdigest()
        if image_hash != self._last_canvas_image_hash:
            self._last_canvas_image_hash = image_hash
            self._pending_vision_trigger = True

        while not self._image_queue.empty():
            try:
                self._image_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        try:
            self._image_queue.put_nowait((image_bytes, mime))
        except asyncio.QueueFull:
            pass

    async def stop(self):
        await self.stop_session()

    def set_mute_state(self, muted: bool):
        self._muted = bool(muted)
        print(f"[Agent] Mute state set: muted={self._muted}")

    def _send_content(self, parts: list[types.Part]):
        if not self.running or not self._live_queue:
            return
        self._live_queue.send_content(content=types.Content(role="user", parts=parts))

    async def _emit(self, msg_type: str, payload: dict):
        enriched = {**payload, "ts": time.time()}
        await self.broadcast_fn({"type": msg_type, "payload": enriched})

    async def _on_provocation_ready(self):
        if not self.running or not self._ready.is_set() or self.mode != "think":
            return

        prompt = (
            "The user has paused — both voice and canvas are still. "
            "Find one idea that deserves a genuine open question. "
            "Place a single violet sticky note — the question only, nothing else. "
            "If nothing genuinely stands out, do nothing. "
            "No audio. No explanation."
        )

        if self._image_queue.empty():
            self._send_content([types.Part(text=prompt)])
            return

        try:
            frame, frame_mime = self._image_queue.get_nowait()
        except asyncio.QueueEmpty:
            return

        self._send_content([
            types.Part(inline_data=types.Blob(data=frame, mime_type=frame_mime)),
            types.Part(text=prompt),
        ])
        get_event_bus().signal_provocation_placed()
        print("[Agent] Provocation triggered (event-driven silence)")

    def _build_run_config(self) -> RunConfig:
        response_modalities = [types.Modality.AUDIO] if self._audio_live_enabled else [types.Modality.TEXT]
        speech_config = None
        if self._audio_live_enabled:
            speech_config = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            )

        return RunConfig(
            streaming_mode=StreamingMode.BIDI,
            speech_config=speech_config,
            response_modalities=response_modalities,
            session_resumption=types.SessionResumptionConfig() if self._audio_live_enabled else None,
        )

    async def _run_session(self):
        persona = await memory_store().read(USER_ID)

        reconnect_attempts = 0
        try:
            while True:
                # Voice remains the default. On specific protocol errors, we allow
                # one immediate text fallback attempt, then return to voice default.
                if self._use_text_fallback_once:
                    self._audio_live_enabled = False
                    self._active_live_model = FAST_MODEL
                    self._use_text_fallback_once = False
                else:
                    self._audio_live_enabled = True
                    self._active_live_model = LIVE_MODEL

                active_session_id = SESSION_ID if self._audio_live_enabled else f"{SESSION_ID}_text"
                self._active_session_id = active_session_id
                agent = create_agent(
                    self.mode,
                    self.web_search,
                    persona,
                    model_name=self._active_live_model,
                )

                self._runner = Runner(
                    agent=agent,
                    app_name=APP_NAME,
                    session_service=self._session_service,
                )

                session = await self._session_service.get_session(
                    app_name=APP_NAME,
                    user_id=USER_ID,
                    session_id=active_session_id,
                )
                if session is None:
                    session = await self._session_service.create_session(
                        app_name=APP_NAME,
                        user_id=USER_ID,
                        session_id=active_session_id,
                    )

                print(
                    "[Agent] Session open — "
                    f"mode={self.mode} web_search={self.web_search} "
                    f"model={self._active_live_model} audio_live={self._audio_live_enabled} "
                    f"session_id={self._active_session_id} "
                    f"persona_keys={list(persona.keys())}"
                )

                self._session = session
                self._live_queue = LiveRequestQueue()
                self.running = True
                self._session_started_at = time.monotonic()
                self._ready.clear()
                self._recoverable_live_disconnect = False
                get_event_bus().reset_timers()

                _lq = self._live_queue

                def _nudge(text: str):
                    if self.running and _lq:
                        try:
                            _lq.send_content(
                                content=types.Content(role="user", parts=[types.Part(text=text)])
                            )
                        except Exception as exc:
                            print(f"[Agent] Nudge failed: {exc}")

                from sub_agents.persona_agent import get_persona_agent
                get_persona_agent().set_nudge_fn(_nudge)

                await self._emit("ai_status", {"status": "idle"})

                try:
                    await asyncio.gather(
                        self._send_loop(),
                        self._receive_loop(self._build_run_config()),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    print(f"[Agent] Session task failed: {exc}")

                if self._recoverable_live_disconnect and self._emit_disconnected_on_exit and reconnect_attempts < 3:
                    reconnect_attempts += 1
                    wait_seconds = min(6.0, 1.5 * reconnect_attempts)
                    print(f"[Agent] Live connection dropped (transient). Reconnecting in {wait_seconds:.1f}s...")
                    await asyncio.sleep(wait_seconds)
                    continue

                break
        finally:
            self.running = False
            self._ready.clear()
            if self._live_queue is not None:
                self._live_queue.close()
            from sub_agents.persona_agent import get_persona_agent
            get_persona_agent().set_nudge_fn(None)
            if self._emit_disconnected_on_exit:
                await self._emit("ai_status", {"status": "disconnected"})
            self._emit_disconnected_on_exit = True

    async def _send_loop(self):
        self._ready.set()
        if self._audio_live_enabled:
            print("[Agent] Ready — mic live")
        else:
            print("[Agent] Ready — text live mode (audio disabled)")

        image_interval = 5.0
        min_image_gap = 1.5

        while self.running and self._live_queue is not None:
            try:
                chunks: list[bytes] = []
                while not self._audio_queue.empty():
                    try:
                        chunks.append(self._audio_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                if chunks:
                    if self._audio_live_enabled:
                        self._live_queue.send_realtime(
                            types.Blob(data=b"".join(chunks), mime_type="audio/pcm;rate=16000")
                        )

                now = time.monotonic()
                should_send_image = (
                    not self._image_queue.empty()
                    and ((now - self._last_image_sent) >= image_interval or self._pending_vision_trigger)
                    and (now - self._last_image_sent) >= min_image_gap
                )

                if should_send_image:
                    try:
                        frame, frame_mime = self._image_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        frame = None
                        frame_mime = None

                    if frame is not None and frame_mime is not None:
                        if self._audio_live_enabled:
                            self._live_queue.send_realtime(types.Blob(data=frame, mime_type=frame_mime))
                        else:
                            # Text fallback sessions don't reliably support realtime blobs.
                            self._send_content([types.Part(inline_data=types.Blob(data=frame, mime_type=frame_mime))])
                        self._last_image_sent = now

                        session_warm = (now - self._session_started_at) >= 8.0
                        required_quiet = self._agent_quiet_required
                        agent_quiet = (now - self._last_tool_call_time) >= required_quiet
                        cooldown_ok = (now - self._last_vision_trigger) >= self._vision_trigger_cooldown
                        mode_allows_proactive = self.mode == "think"

                        if self._pending_vision_trigger and session_warm and agent_quiet and cooldown_ok and mode_allows_proactive:
                            proactive_text = (
                                "The user has made new changes to the canvas. "
                                "Look at what was added or changed. "
                                "Only act if there is a specific and immediate opportunity, "
                                "such as an unanswered question, an obvious missing connection, "
                                "or a direct gap you can fill with one action. "
                                "If no clear opportunity exists, stay completely silent."
                            )
                            self._send_content([types.Part(text=proactive_text)])
                            self._last_vision_trigger = now
                            self._pending_vision_trigger = False
                            print("[Agent] Proactive vision trigger fired")

                await asyncio.sleep(0.05)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[Agent] Send loop error: {exc}")
                break

    async def _receive_loop(self, run_config: RunConfig):
        assert self._runner is not None
        assert self._live_queue is not None

        try:
            async for event in self._runner.run_live(
                user_id=USER_ID,
                session_id=self._active_session_id,
                session=self._session,
                live_request_queue=self._live_queue,
                run_config=run_config,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if getattr(part, "inline_data", None):
                            audio_data = part.inline_data.data
                            if audio_data and not self._muted:
                                self._is_speaking = True
                                await self._emit("ai_status", {"status": "speaking"})
                                await self._emit("audio_response", {
                                    "data": base64.b64encode(audio_data).decode(),
                                    "format": "pcm16",
                                    "sample_rate": 24000,
                                })

                function_calls = event.get_function_calls()
                if function_calls:
                    self._last_tool_call_time = time.monotonic()
                    for call in function_calls:
                        print(f"[Agent] Tool call: {call.name} args={call.args}")
                    await self._emit("ai_status", {"status": "thinking"})

                if getattr(event, "interrupted", False):
                    now = time.monotonic()
                    should_emit = self._is_speaking or (now - self._last_interrupt_emit) >= self._interrupt_emit_cooldown
                    if should_emit:
                        self._is_speaking = False
                        self._last_interrupt_emit = now
                        print("[Agent] Barge-in — flushing frontend audio")
                        await self._emit("ai_interrupted", {})
                        await self._emit("ai_status", {"status": "idle"})

                if getattr(event, "turn_complete", False):
                    self._is_speaking = False
                    await self._emit("ai_status", {"status": "idle"})

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            msg = str(exc)
            unsupported_live_mode = (
                "1008" in msg
                and (
                    "not implemented" in msg.lower()
                    or "not supported" in msg.lower()
                    or "not enabled" in msg.lower()
                )
            )
            voice_mismatch_mode = (
                "1007" in msg
                and "cannot extract voices from a non-audio request" in msg.lower()
            )
            invalid_argument_mode = (
                "1007" in msg
                and "invalid argument" in msg.lower()
            )
            recoverable = (
                "1006" in msg
                or "1011" in msg
                or "deadline expired" in msg.lower()
                or "keepalive ping timeout" in msg
                or "abnormal closure" in msg
            )
            if unsupported_live_mode and self._audio_live_enabled:
                print("[Agent] Live audio mode unsupported by current model/account. Falling back to text-only live mode.")
                self._use_text_fallback_once = True
                self._recoverable_live_disconnect = True
            elif voice_mismatch_mode:
                print("[Agent] Voice config mismatch in text mode. Reconnecting with text model/session only.")
                self._use_text_fallback_once = True
                self._recoverable_live_disconnect = True
            elif invalid_argument_mode:
                print("[Agent] Live request rejected (1007 invalid argument). Reconnecting in fallback text mode.")
                self._use_text_fallback_once = True
                self._recoverable_live_disconnect = True
            elif recoverable:
                print(f"[Agent] Receive loop transient disconnect: {msg}")
                self._recoverable_live_disconnect = True
            else:
                print(f"[Agent] Receive loop error: {exc}")
                import traceback
                traceback.print_exc()
            self.running = False
            self._ready.clear()
            if self._live_queue is not None:
                self._live_queue.close()
