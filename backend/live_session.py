import asyncio
import base64
import os
import time
from typing import Callable, Awaitable

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

import tools as canvas_tools
from event_bus import get_event_bus
from memory import memory_store
from agent import create_agent

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

        self._live_queue: LiveRequestQueue | None = None
        self._runner: Runner | None = None
        self._session = None
        self.running = False
        self._last_image_sent: float = 0.0
        self._ready = asyncio.Event()
        self._restart_requested = False

        bus = get_event_bus()
        bus.subscribe("provocation_ready", self._on_provocation_ready)

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
            self._live_queue.close()

    def push_audio(self, pcm_bytes: bytes):
        if self.running and self._ready.is_set():
            get_event_bus().signal_audio()
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

    async def _on_provocation_ready(self):
        if not self.running or not self._ready.is_set():
            return
        if self.mode != "think":
            return

        if self._image_queue.empty():
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

    async def _run_session(self):
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
        self._ready.set()
        print("[Agent] Ready — mic live")

        IMAGE_INTERVAL = 20.0

        while self.running:
            try:
                chunks = []
                while not self._audio_queue.empty():
                    try: chunks.append(self._audio_queue.get_nowait())
                    except asyncio.QueueEmpty: break
                if chunks:
                    self._live_queue.send_realtime(
                        types.Blob(data=b"".join(chunks), mime_type="audio/pcm;rate=16000")
                    )

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

                if event.get_function_calls():
                    await self.broadcast_fn({"type": "ai_status", "payload": {"status": "thinking"}})

                if getattr(event, "interrupted", False):
                    print("[Agent] Barge-in — flushing frontend audio")
                    await self.broadcast_fn({"type": "ai_interrupted", "payload": {}})
                    await self.broadcast_fn({"type": "ai_status", "payload": {"status": "idle"}})

                if event.turn_complete:
                    await self.broadcast_fn({"type": "ai_status", "payload": {"status": "idle"}})

        except Exception as e:
            print(f"[Agent] Receive loop error: {e}")
            import traceback; traceback.print_exc()
        finally:
            self.running = False
            await self.broadcast_fn({"type": "ai_status", "payload": {"status": "disconnected"}})

    async def _action_drain_loop(self):
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
