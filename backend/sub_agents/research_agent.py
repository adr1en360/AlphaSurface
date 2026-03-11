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

Canvas layout: title on left, bullets fanned out to the right.
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
    Broadcast canvas actions to place a research result cluster.
    """
    bx, by = _canvas_pos()

    title_id = _make_shape_id("res_title")
    title_w, title_h = 260, 80
    spacing = 140 if long_form else 110

    # 1 — Title geo (teal/green, solid)
    await broadcast_fn({
        "type": "add_geo",
        "payload": {
            "id": title_id,
            "x": bx,
            "y": by,
            "w": title_w,
            "h": title_h,
            "text": title,
            "color": "blue",
            "fill": "solid",
            "geo": "rectangle",
        }
    })

    await asyncio.sleep(0.15)

    # 2 — Bullets fanned to the right
    start_y = by - ((len(bullets) - 1) * spacing) // 2

    for i, bullet in enumerate(bullets):
        bid = _make_shape_id(f"res_bullet_{i}")
        bul_x = bx + title_w + 120
        bul_y = start_y + i * spacing

        if long_form:
            await broadcast_fn({
                "type": "add_text",
                "payload": {
                    "id": bid, "x": bul_x, "y": bul_y,
                    "text": bullet, "size": "s", "color": "black",
                }
            })
        else:
            await broadcast_fn({
                "type": "add_note",
                "payload": {
                    "id": bid, "x": bul_x, "y": bul_y,
                    "text": bullet, "color": "blue",
                }
            })
        await asyncio.sleep(0.1)

        arrow_id = _make_shape_id(f"res_arrow_{i}")
        await broadcast_fn({
            "type": "add_arrow",
            "payload": {
                "id": arrow_id,
                "x1": bx + title_w, "y1": by + title_h // 2,
                "x2": bul_x, "y2": bul_y + (20 if long_form else 60),
            }
        })
        await asyncio.sleep(0.08)

    # 3 — Source bookmark below title (if available)
    if source_url:
        bm_id = _make_shape_id("res_source")
        await broadcast_fn({
            "type": "add_bookmark",
            "payload": {
                "id": bm_id,
                "x": bx,
                "y": by + title_h + 20,
                "url": source_url,
            }
        })
        await asyncio.sleep(0.1)

    # 4 — Agent attribution stamp
    stamp_id = _make_shape_id("res_stamp")
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "id": stamp_id,
            "x": bx,
            "y": by - 28,
            "text": "ResearchAgent" + (" · long form" if long_form else ""),
            "size": "s",
            "color": "green",
        }
    })
    await asyncio.sleep(0.05)

    # 5 — Zoom to fit
    await broadcast_fn({"type": "zoom_to_fit", "payload": {}})
    print(f"[ResearchAgent] Cluster placed — '{title}' with {len(bullets)} bullets ({'long' if long_form else 'short'} form)")


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

