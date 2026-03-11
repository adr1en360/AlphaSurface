"""
AlphaSurface — PersonaAgent (Lane 1: Context Provider)

Role: Continuously profile the user from what they write on canvas
      and how they interact. Updates memory silently.

Does NOT act on the canvas. Does NOT speak.
Exists purely to make every other agent smarter.

How it works:
  - Subscribes to canvas_changed and user_silent events
  - On trigger: calls ADK Agent with all canvas text + current profile
  - Extracts traits, updates memory
  - Every agent reads this profile at session start via memory_read

Persona fields tracked:
  communication_style    — verbose | concise | visual | textual
  domain                 — what topics the user works on
  thinking_pattern       — associative | structured | exploratory
  response_preference    — diagrams | text | questions | answers
  provocation_preference — specific | abstract | frequent | rare
  observed_traits        — list of observed behaviours (append-only)
  session_count          — how many sessions completed
"""

import asyncio
import json
from typing import Optional

from pydantic import BaseModel, Field

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from event_bus import get_event_bus
from memory import memory_store
import tools as canvas_tools

USER_ID = "user"


class PersonaUpdates(BaseModel):
    updates: dict[str, str] = Field(description="Dictionary of persona field updates. Keys from tracked fields.")
    append_traits: list[str] = Field(description="List of specific, behavioural traits to append.", default_factory=list)


_PERSONA_SYSTEM = """
You are analysing a user's whiteboard to build a profile of how they think and communicate.
You will receive:
  1. All text currently on their canvas (shapes, notes, labels)
  2. Their current stored profile (may be empty for new users)

Your job: extract 1-3 genuine observations about this specific person.
Focus on:
  - How they write (terse vs verbose, structured vs freeform)
  - What domain they work in (infer from topic vocabulary)
  - What they seem to want from an AI (answers? questions? resources?)
  - Any explicit preferences they wrote down

Rules:
  - Only include keys in `updates` where you have genuine evidence from the canvas
  - `append_traits` should be specific and behavioural, e.g.:
      "writes in bullet fragments, not full sentences"
      "connects concepts with arrows before labelling them"
      "explicit about what they don't know"
  - Do NOT invent traits. If you see nothing useful, return empty dict and empty list.
  - Do NOT include keys from the existing profile unless you're updating them with new evidence
"""


class PersonaAgent:
    def __init__(self):
        self._running = False
        self._analysis_lock = asyncio.Lock()
        self._pending_analysis = False
        self._nudge_fn = None
        self._session_service = InMemorySessionService()

    def set_nudge_fn(self, fn):
        """
        Register a callable the Live Agent exposes so PersonaAgent can
        push silent mid-session updates directly into the live queue.
        fn signature: fn(text: str) — sends a silent content message.
        """
        self._nudge_fn = fn

    def start(self):
        """Register event subscriptions and mark as running."""
        bus = get_event_bus()
        bus.subscribe("canvas_changed", self._queue_analysis)
        bus.subscribe("user_silent", self._queue_analysis)
        self._running = True
        print("[PersonaAgent] Running — watching canvas for user traits")

    def stop(self):
        self._running = False

    async def _queue_analysis(self):
        """
        Debounce: if an analysis is already queued or running, skip.
        This prevents a flood of analyses when the canvas changes rapidly.
        """
        if self._pending_analysis or not self._running:
            return
        self._pending_analysis = True
        # Small delay so rapid changes settle before we read the canvas
        await asyncio.sleep(3.0)
        self._pending_analysis = False
        await self._analyze()

    async def _analyze(self):
        """Read canvas text, call ADK Agent, update memory."""
        async with self._analysis_lock:
            try:
                canvas_text = canvas_tools.scan_canvas_text()
                total = canvas_text.get("total_text_shapes", 0)
                if total == 0:
                    return  # Nothing to analyse yet

                current_profile = await memory_store().read(USER_ID)

                # Build prompt
                canvas_summary = _format_canvas_for_analysis(canvas_text)
                profile_summary = json.dumps(current_profile, indent=2) if current_profile else "{}"

                user_message_text = (
                    f"Canvas content:\n{canvas_summary}\n\n"
                    f"Current profile:\n{profile_summary}"
                )

                # Create the ADK Agent
                analysis_agent = Agent(
                    name="persona_analysis_agent",
                    model="gemini-2.5-flash",
                    instruction=_PERSONA_SYSTEM,
                    output_schema=PersonaUpdates,
                    output_key="persona_updates",
                    generate_content_config=types.GenerateContentConfig(
                        temperature=0.3,
                    ),
                )

                await self._session_service.create_session(
                    app_name="alphasurface", user_id=USER_ID, session_id="persona_session"
                )

                runner = Runner(
                    agent=analysis_agent,
                    app_name="alphasurface",
                    session_service=self._session_service,
                )

                message = types.Content(
                    role="user", parts=[types.Part.from_text(text=user_message_text)]
                )

                async for event in runner.run_async(
                    user_id=USER_ID, session_id="persona_session", new_message=message
                ):
                    pass # We just want the final state
                
                session = await self._session_service.get_session("alphasurface", USER_ID, "persona_session")
                if not session or "persona_updates" not in session.state:
                    return

                parsed: dict = session.state["persona_updates"]

                updates = parsed.get("updates", {})
                new_traits = parsed.get("append_traits", [])

                if updates or new_traits:
                    if new_traits:
                        existing_traits = current_profile.get("observed_traits", [])
                        merged_traits = existing_traits[:]
                        for t in new_traits:
                            if t not in merged_traits:
                                merged_traits.append(t)
                        updates["observed_traits"] = merged_traits

                    await memory_store().merge(USER_ID, updates)
                    print(f"[PersonaAgent] Profile updated: {list(updates.keys())}")

                    # Real-time nudge → Live Agent absorbs mid-session
                    if self._nudge_fn:
                        summary = _build_nudge_summary(updates)
                        if summary:
                            self._nudge_fn(summary)
                            print(f"[PersonaAgent] Nudge sent: {summary}")

            except Exception as e:
                print(f"[PersonaAgent] Analysis error: {e}")

    async def increment_session_count(self):
        """Call this at session start to track how many sessions the user has had."""
        profile = await memory_store().read(USER_ID)
        count = profile.get("session_count", 0) + 1
        await memory_store().merge(USER_ID, {"session_count": count})
        return count


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_canvas_for_analysis(canvas_text: dict) -> str:
    lines = []
    for note in canvas_text.get("sticky_notes", []):
        lines.append(f"[sticky note] {note['text']}")
    for geo in canvas_text.get("geo_shapes", []):
        lines.append(f"[shape label] {geo['text']}")
    for txt in canvas_text.get("text_labels", []):
        lines.append(f"[text] {txt['text']}")
    for other in canvas_text.get("other", []):
        lines.append(f"[shape] {other['text']}")
    return "\n".join(lines) if lines else "(empty canvas)"


def _build_nudge_summary(updates: dict) -> str:
    """
    Converts a persona update dict into a short silent instruction
    the Live Agent can absorb without speaking aloud.
    """
    lines = []
    for k, v in updates.items():
        if k == "observed_traits" and isinstance(v, list):
            # Only send the most recent trait, not the whole list
            if v:
                lines.append(f"user trait observed: {v[-1]}")
        elif k != "_prev_ids":
            lines.append(f"{k}: {v}")
    if not lines:
        return ""
    return "Silent persona update — do not speak this aloud. Adjust your behaviour accordingly. " + "; ".join(lines)


# ── Singleton ──────────────────────────────────────────────────────────────────

_persona_agent: PersonaAgent | None = None


def get_persona_agent() -> PersonaAgent:
    global _persona_agent
    if _persona_agent is None:
        _persona_agent = PersonaAgent()
    return _persona_agent

