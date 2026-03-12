"""
AlphaSurface — ResearchAgent

Triggered by:
  A) Live Agent calls dispatch_research("query") → task lands in queue
  B) (Future) Event bus fires research_ready on long idle + canvas topic detected

Flow:
  1. Receives {query: str} payload from dispatcher
  2. Runs ADK Agent with google_search tool to get real results
  3. Returns structured JSON (Pydantic model): title + bullets + sources
  4. Places a clean cluster on canvas:
       [Title geo] ──→ [Bullet note] x3-5
                   ──→ [Source bookmark] (if URL available)
  5. Calls signal_agent_acted() via dispatcher wrapper (already done)

Canvas layout: newspaper-style single column with headline + sections.
All shapes placed relative to current viewport center.
"""

import asyncio
import os
import random
from typing import Optional

from pydantic import BaseModel, Field

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search
from google.genai import types

from event_bus import get_event_bus
from sub_agents import emit_failure_note

# ── Agent identity ───────────────────────────────────────────────────────────
# Each agent stamps its output with a small attribution label on canvas.

# ── Config ────────────────────────────────────────────────────────────────────

_MODEL = "gemini-2.5-flash"

_SYSTEM_PROMPT = """\
You are a research assistant. Your job is to search the web for information on a query
and return a structured summary suitable for placing on a visual canvas.

Rules:
- 3 to 5 bullets maximum
- Each bullet must be a concrete fact or finding, not a vague statement
- Prefer recent information
- ALWAYS use the google_search tool to find accurate information. DO NOT guess.
"""

class ResearchResult(BaseModel):
    title: str = Field(description="Short topic title (max 5 words)")
    format: str = Field(
        description=(
            "'long' for conceptual/explanatory questions (explain, history, how does, why). "
            "'short' for quick facts, comparisons, or lookups. Default: 'short'."
        )
    )
    bullets: list[str] = Field(
        description=(
            "Key findings. 'short': 3-5 concise one-sentence bullets. "
            "'long': 5-8 detailed points with full context and specifics."
        )
    )
    source_url: Optional[str] = Field(description="URL of best single source, or null")
    source_label: Optional[str] = Field(description="Short label for the source e.g. 'Reuters' or null")


# ── Canvas placement helpers ──────────────────────────────────────────────────

def _canvas_pos():
    """Return a base (x, y) position offset from canvas center with slight randomness."""
    base_x = random.randint(-600, 200)
    base_y = random.randint(-300, 300)
    return base_x, base_y


def _make_shape_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _place_cluster(broadcast_fn, title: str, bullets: list[str],
                          source_url: str | None, source_label: str | None,
                          long_form: bool = False):
    """
    Broadcast canvas actions in a newspaper-column layout (no frame — avoids overlap).
    Shapes are placed as free-floating elements in a clean vertical column.
    """
    bx, by = _canvas_pos()

    col_w = 480
    # Larger bullet boxes so text has room to breathe
    bullet_h = 150 if long_form else 110
    bullet_gap = 16

    # ── Masthead ──────────────────────────────────────────────────────────────
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "id": _make_shape_id("res_masthead"),
            "x": bx,
            "y": by,
            "text": "RESEARCH DESK",
            "size": "s",
            "color": "grey",
        }
    })
    await asyncio.sleep(0.04)

    # ── Headline box ──────────────────────────────────────────────────────────
    await broadcast_fn({
        "type": "add_geo",
        "payload": {
            "id": _make_shape_id("res_headline"),
            "x": bx,
            "y": by + 24,
            "w": col_w,
            "h": 70,
            "text": title,
            "color": "black",
            "fill": "none",
            "geo": "rectangle",
        }
    })
    await asyncio.sleep(0.06)

    # ── Thin divider ──────────────────────────────────────────────────────────
    await broadcast_fn({
        "type": "add_geo",
        "payload": {
            "id": _make_shape_id("res_divider"),
            "x": bx,
            "y": by + 98,
            "w": col_w,
            "h": 3,
            "text": "",
            "color": "grey",
            "fill": "solid",
            "geo": "rectangle",
        }
    })
    await asyncio.sleep(0.04)

    # ── Numbered bullet blocks ────────────────────────────────────────────────
    body_start_y = by + 108
    for i, bullet in enumerate(bullets):
        block_y = body_start_y + i * (bullet_h + bullet_gap)
        await broadcast_fn({
            "type": "add_geo",
            "payload": {
                "id": _make_shape_id(f"res_col_{i}"),
                "x": bx,
                "y": block_y,
                "w": col_w,
                "h": bullet_h,
                "text": f"{i + 1:02d}.  {bullet}",
                "color": "blue",
                "fill": "none",
                "geo": "rectangle",
            }
        })
        await asyncio.sleep(0.08)

    # ── Source footer ─────────────────────────────────────────────────────────
    footer_y = body_start_y + len(bullets) * (bullet_h + bullet_gap) + 12
    source_label_text = source_label or "Source"
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "id": _make_shape_id("res_source_strip"),
            "x": bx,
            "y": footer_y,
            "text": f"{source_label_text} · fact-checked",
            "size": "s",
            "color": "green",
        }
    })
    await asyncio.sleep(0.04)

    if source_url:
        await broadcast_fn({
            "type": "add_bookmark",
            "payload": {
                "id": _make_shape_id("res_source"),
                "x": bx,
                "y": footer_y + 22,
                "url": source_url,
            }
        })
        await asyncio.sleep(0.1)

    # ── Attribution ───────────────────────────────────────────────────────────
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "id": _make_shape_id("res_stamp"),
            "x": bx + col_w - 180,
            "y": footer_y + (120 if source_url else 20),
            "text": "ResearchAgent" + (" · long form" if long_form else " · brief"),
            "size": "s",
            "color": "grey",
        }
    })
    await asyncio.sleep(0.05)

    await broadcast_fn({"type": "zoom_to_fit", "payload": {}})
    print(f"[ResearchAgent] Newspaper column placed — '{title}' with {len(bullets)} items ({'long' if long_form else 'short'} form)")


# ── Core research logic ───────────────────────────────────────────────────────

async def run_research(payload: dict, broadcast_fn) -> None:
    """
    Main handler. Called by dispatcher with payload = {"query": str}.
    """
    query = payload.get("query", "").strip()
    if not query:
        print("[ResearchAgent] Empty query — skipping")
        return

    print(f"[ResearchAgent] Researching: {query}")

    try:
        # ADK Agents cannot use both tools and output_schema directly.
        # We use a SequentialAgent pipeline: fetch -> format
        from google.adk.agents import SequentialAgent
        
        research_fetcher = Agent(
            name="research_fetcher",
            model=_MODEL,
            instruction=_SYSTEM_PROMPT,
            tools=[google_search],
            output_key="raw_research",
            generate_content_config=types.GenerateContentConfig(temperature=0.2),
        )

        research_formatter = Agent(
            name="research_formatter",
            model=_MODEL,
            instruction="Format this research into the structured schema: {raw_research}",
            output_schema=ResearchResult,
            output_key="research_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=types.GenerateContentConfig(temperature=0),
        )

        research_agent = SequentialAgent(
            name="research_pipeline",
            sub_agents=[research_fetcher, research_formatter]
        )

        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="alphasurface", user_id="user", session_id="research_session"
        )
        
        runner = Runner(
            agent=research_agent,
            app_name="alphasurface",
            session_service=session_service,
        )

        message = types.Content(
            role="user", parts=[types.Part.from_text(text=f"Research this topic: {query}")]
        )

        final_state = None
        async for event in runner.run_async(
            user_id="user", session_id="research_session", new_message=message
        ):
            if event.is_final_response():
                pass

        session = await session_service.get_session(
            app_name="alphasurface", user_id="user", session_id="research_session"
        )
        if not session or "research_result" not in session.state:
            print("[ResearchAgent] Failed to retrieve valid schema response.")
            return
            
        result: dict = session.state["research_result"]

        title = result.get("title", query[:40])
        long_form = result.get("format", "short") == "long"
        max_bullets = 8 if long_form else 5
        bullets = result.get("bullets", [])[:max_bullets]
        source_url = result.get("source_url")
        source_label = result.get("source_label")

        if not bullets:
            print("[ResearchAgent] No bullets returned — skipping canvas placement")
            return

        await _place_cluster(broadcast_fn, title, bullets, source_url, source_label, long_form=long_form)

    except Exception as e:
        print(f"[ResearchAgent] Error: {e}")
        import traceback
        traceback.print_exc()
        await emit_failure_note(broadcast_fn, "ResearchAgent", e)

