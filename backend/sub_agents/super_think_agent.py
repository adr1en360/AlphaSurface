"""
AlphaSurface — SuperThinkAgent

A deep canvas analysis sub-agent. Triggered when the user explicitly says something
like "super think", "deep dive", "analyze this", or "think harder".

Flow:
  1. Reads all text from the canvas (via the canvas_state snapshot)
  2. Sends it to gemini-2.5-pro with extended thinking budget
  3. Places 3 tiers of output on canvas:
       - 🟣 Core insight cluster (synthesis of what's on canvas)
       - 🔴 Tensions / contradictions found
       - 🟡 Open questions / white-space (what's missing)
  4. Zoom to fit

Model: gemini-2.5-pro (thinking model — best for deep reasoning)
"""

import asyncio
import random
from typing import Optional

from google.genai import Client, types
import os
from model_config import THINKING_MODEL
from sub_agents import emit_failure_note

# ── Config ────────────────────────────────────────────────────────────────────

_MODEL = THINKING_MODEL
_THINKING_BUDGET = 8192  # tokens dedicated to internal reasoning

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_shape_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _canvas_pos():
    """Return a base position offset from canvas center with slight randomness."""
    bx = random.randint(-800, -200)
    by = random.randint(-400, 300)
    return bx, by


_genai_client: Optional[Client] = None

def _get_client() -> Client:
    global _genai_client
    if _genai_client is None:
        _genai_client = Client(api_key=os.getenv("GEMINI_API_KEY", ""))
    return _genai_client


# ── Deep analysis prompt ──────────────────────────────────────────────────────

_SYSTEM = """\
You are a deep analytical thinker reviewing a shared thinking canvas.
The canvas contains the user's ideas, notes, sketches, and concepts.

Your task is to produce THREE layers of analysis:

1. SYNTHESIS (2-3 bullet points):
   What is the core insight or claim the user is building?
   What do all these ideas have in common?

2. TENSIONS (2-3 bullet points):
   What contradictions, trade-offs, or unresolved conflicts exist in these ideas?
   What assumptions are being made that could be challenged?

3. OPEN QUESTIONS (2-3 bullet points):
   What important question has NOT been asked yet?
   What would make this thinking more complete?

Format your response as:
SYNTHESIS:
• [point]
• [point]

TENSIONS:
• [point]
• [point]

OPEN QUESTIONS:
• [point]
• [point]

Be specific. Reference the actual content on the canvas, not generic advice.
If the canvas is empty or has only shapes with no text, say so in SYNTHESIS.
"""

# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_sections(text: str) -> dict[str, list[str]]:
    """Parse the three-section response into lists of bullet points."""
    sections: dict[str, list[str]] = {
        "synthesis": [],
        "tensions": [],
        "open_questions": [],
    }
    current: Optional[str] = None
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("SYNTHESIS"):
            current = "synthesis"
        elif line.upper().startswith("TENSION"):
            current = "tensions"
        elif line.upper().startswith("OPEN QUESTION"):
            current = "open_questions"
        elif line.startswith("•") or line.startswith("-") or line.startswith("*"):
            if current:
                bullet = line.lstrip("•-* ").strip()
                if bullet:
                    sections[current].append(bullet)
    return sections


# ── Canvas placement ──────────────────────────────────────────────────────────

_SECTION_COLORS = {
    "synthesis": "violet",
    "tensions": "red",
    "open_questions": "yellow",
}

_SECTION_LABELS = {
    "synthesis": "💡 Synthesis",
    "tensions": "⚡ Tensions",
    "open_questions": "❓ Open Questions",
}


async def _place_super_think(broadcast_fn, sections: dict[str, list[str]]):
    """Place three analysis clusters vertically on canvas."""
    bx, by = _canvas_pos()
    col_gap = 420
    note_h = 120
    note_w = 380
    note_spacing = 140

    for col, (key, bullets) in enumerate(sections.items()):
        if not bullets:
            continue

        cx = bx + col * col_gap
        cy = by

        # Section header (geo shape)
        header_id = _make_shape_id(f"st_{key}_header")
        await broadcast_fn({
            "type": "add_geo",
            "payload": {
                "id": header_id,
                "x": cx,
                "y": cy,
                "w": note_w,
                "h": 54,
                "text": _SECTION_LABELS[key],
                "color": _SECTION_COLORS[key],
                "fill": "solid",
                "geo": "rectangle",
            }
        })
        await asyncio.sleep(0.1)

        # Bullet notes below header
        for i, bullet in enumerate(bullets[:3]):
            note_id = _make_shape_id(f"st_{key}_{i}")
            await broadcast_fn({
                "type": "add_note",
                "payload": {
                    "id": note_id,
                    "x": cx,
                    "y": cy + 70 + i * note_spacing,
                    "text": bullet,
                    "color": _SECTION_COLORS[key],
                }
            })
            await asyncio.sleep(0.08)

    # Attribution
    stamp_id = _make_shape_id("st_stamp")
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "id": stamp_id,
            "x": bx,
            "y": by - 32,
            "text": f"🧠 SuperThink · {_MODEL}",
            "size": "s",
            "color": "violet",
        }
    })
    await asyncio.sleep(0.05)

    await broadcast_fn({"type": "zoom_to_fit", "payload": {}})


# ── Canvas text extractor ─────────────────────────────────────────────────────

def _extract_canvas_text(canvas_state: dict) -> str:
    """Pull all text from the canvas shapes into a flat summary."""
    shapes = canvas_state.get("shapes", [])
    lines = []
    non_text_counts: dict[str, int] = {}
    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        text = (shape.get("text") or shape.get("label") or "").strip()
        if text:
            shape_type = shape.get("type", "shape")
            lines.append(f"[{shape_type}] {text}")
        else:
            shape_type = shape.get("type", "shape")
            non_text_counts[shape_type] = non_text_counts.get(shape_type, 0) + 1

    if lines:
        return "\n".join(lines)

    if shapes:
        summary = ", ".join(f"{k}:{v}" for k, v in sorted(non_text_counts.items()))
        return f"(canvas has {len(shapes)} shapes with no readable text labels; types: {summary})"

    return "(canvas is empty)"


# ── Main handler ──────────────────────────────────────────────────────────────

async def run_super_think(payload: dict, broadcast_fn, canvas_state: dict) -> None:
    """
    Main handler. Called by dispatcher with payload = {'trigger': str}.
    canvas_state: the live canvas state dict from tools.canvas_state.
    """
    print("[SuperThink] Starting deep analysis...")

    canvas_text = _extract_canvas_text(canvas_state)
    print(f"[SuperThink] Canvas content ({len(canvas_state.get('shapes', []))} shapes):\n{canvas_text[:400]}")

    try:
        client = _get_client()

        user_message = f"Here is what's on the canvas:\n\n{canvas_text}"

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=_MODEL,
            contents=[user_message],
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=_THINKING_BUDGET,
                ),
                temperature=1.0,  # required for thinking models
            ),
        )

        raw_text = response.text.strip()
        print(f"[SuperThink] Response received ({len(raw_text)} chars)")

        sections = _parse_sections(raw_text)
        total_bullets = sum(len(v) for v in sections.values())

        if total_bullets == 0:
            print("[SuperThink] No structured output parsed — skipping canvas placement.")
            return

        await _place_super_think(broadcast_fn, sections)
        print(f"[SuperThink] Complete — {total_bullets} insights placed on canvas.")

    except Exception as e:
        print(f"[SuperThink] Error: {e}")
        msg = str(e)
        is_rate_limited = "429" in msg or "RESOURCE_EXHAUSTED" in msg
        if not is_rate_limited:
            import traceback
            traceback.print_exc()
        await emit_failure_note(broadcast_fn, "SuperThinkAgent", e)
