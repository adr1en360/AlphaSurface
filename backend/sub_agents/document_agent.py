"""
AlphaSurface — DocumentAgent

Mode-aware document handler:

PRESENT MODE (silent):
  - Extracts text from document
  - Stores full text in session memory so the Live Agent can answer
    questions grounded in the actual content
  - Places ONE small green confirmation note: "📄 [filename] loaded"
  - Nothing else touches the canvas — the presenter stays in control

THINK MODE (spatial map):
  - Extracts text and runs ADK analysis
  - Places a structured canvas layout:
      [Title card]
           ↓
      [Summary note]
           ↓
      [Insight 1] → [Insight 2] → [Insight 3] ...
  - Uses viewport context for clean placement
  - No random coordinates, no radiating trigonometry

Triggered by:
  Live Agent calls dispatch_document("query", mode="think"|"explain")
"""

import asyncio
import math
import os
import uuid
from typing import Optional, List

from pydantic import BaseModel, Field

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from model_config import FAST_MODEL
from sub_agents import emit_failure_note
from tools.state import canvas_state
from memory import memory_store

# ── Config ────────────────────────────────────────────────────────────────────

_MODEL = FAST_MODEL
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "documents")


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_text(filepath: str, max_chars: int = 24000) -> str:
    filename = os.path.basename(filepath).lower()
    text = ""
    try:
        if filename.endswith(".pdf"):
            import fitz
            with fitz.open(filepath) as doc:
                for page in doc:
                    text += page.get_text()
                    if len(text) > max_chars:
                        break
        elif filename.endswith(".docx"):
            from docx import Document
            doc = Document(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
                if len(text) > max_chars:
                    break
        elif filename.endswith(".txt"):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
    except Exception as e:
        print(f"[DocumentAgent] Extraction error: {e}")
    return text[:max_chars]


def _find_matching_file(query: str) -> Optional[str]:
    if not os.path.exists(DOCS_DIR):
        return None
    files = os.listdir(DOCS_DIR)
    if not files:
        return None
    query_lower = query.lower()
    for f in files:
        if f.lower() in query_lower or query_lower in f.lower():
            return f
    return files[0]


def _make_id(prefix: str) -> str:
    return f"shape:{prefix}_{uuid.uuid4().hex[:8]}"


# ── ADK Schema ────────────────────────────────────────────────────────────────

class DocumentInsight(BaseModel):
    title: str = Field(description="Short title (max 4 words)")
    content: str = Field(description="Specific finding or data point (max 20 words)")
    importance: str = Field(description="high | medium | low")


class DocumentResult(BaseModel):
    filename: str = Field(description="The filename processed")
    summary: str = Field(description="One sentence summary of the document (max 25 words)")
    insights: List[DocumentInsight] = Field(description="Top 3-5 insights from the document")
    key_questions: List[str] = Field(
        description="2-3 open questions this document raises — for Think Mode provocations",
        default_factory=list
    )


# ── PRESENT MODE: silent load ─────────────────────────────────────────────────

async def _handle_present_mode(filename: str, text: str, broadcast_fn) -> None:
    """
    Present Mode: store document text in memory, place one small confirmation note.
    The Live Agent will be able to answer audience questions grounded in this content.
    """
    # Store in memory so the live agent can reference it
    await memory_store().merge("user", {
        f"document_{filename}": text[:8000],  # store first 8k chars
        "loaded_document": filename,
        "loaded_document_summary": f"Document '{filename}' is loaded and available for reference.",
    })

    # Find a quiet corner for the confirmation note
    vp = canvas_state.get("viewport", {"x": 0, "y": 0, "w": 1200, "h": 800})
    note_x = int(vp["x"] + vp["w"] * 0.02)
    note_y = int(vp["y"] + vp["h"] * 0.02)

    note_id = _make_id("doc_loaded")
    await broadcast_fn({
        "type": "add_note",
        "payload": {
            "id": note_id,
            "x": note_x,
            "y": note_y,
            "text": f"📄 {filename}\nLoaded — agent will reference this during the session.",
            "color": "green",
            "size": "s",
            "meta": {
                "semanticRole": "document_loaded",
                "source": "DocumentAgent",
                "confidence": 1.0,
                "linked_to": [],
                "addedBy": "DocumentAgent",
            }
        }
    })
    print(f"[DocumentAgent] Present Mode — '{filename}' loaded to memory, confirmation note placed.")


# ── THINK MODE: spatial document map ─────────────────────────────────────────

async def _handle_think_mode(filename: str, result: DocumentResult, broadcast_fn) -> None:
    """
    Think Mode: place a structured spatial map of the document on canvas.

    Layout (vertical column, left side of viewport):
    
      [═══ Title card ═══]
               ↓
      [Summary note]
               ↓
      [Insight 1] [Insight 2] [Insight 3]  ← horizontal row
               ↓
      [❓ Question 1]  [❓ Question 2]       ← violet provocations
    """
    vp = canvas_state.get("viewport", {"x": 0, "y": 0, "w": 1200, "h": 800})

    # Anchor: left side of viewport, vertically centered
    base_x = int(vp["x"] - vp["w"] * 0.3)  # just outside left of viewport
    base_y = int(vp["y"] + vp["h"] * 0.1)

    CARD_W = 360
    CARD_H = 80
    NOTE_W = 340
    NOTE_H = 120
    INSIGHT_W = 280
    INSIGHT_H = 100
    GAP_V = 32
    GAP_H = 24

    # ── 1. Title card ──────────────────────────────────────────────────────
    title_id = _make_id("doc_title")
    await broadcast_fn({
        "type": "add_geo",
        "payload": {
            "id": title_id,
            "x": base_x,
            "y": base_y,
            "w": CARD_W,
            "h": CARD_H,
            "text": f"📄  {result.filename}",
            "geo": "rectangle",
            "color": "blue",
            "fill": "solid",
            "size": "m",
            "meta": {"semanticRole": "document_title", "source": "DocumentAgent", "confidence": 1.0, "linked_to": [], "addedBy": "DocumentAgent"}
        }
    })
    await asyncio.sleep(0.08)

    # ── 2. Summary note ────────────────────────────────────────────────────
    summary_y = base_y + CARD_H + GAP_V
    summary_id = _make_id("doc_summary")
    await broadcast_fn({
        "type": "add_note",
        "payload": {
            "id": summary_id,
            "x": base_x + (CARD_W - NOTE_W) // 2,
            "y": summary_y,
            "text": result.summary,
            "color": "blue",
            "size": "m",
            "meta": {"semanticRole": "document_summary", "source": "DocumentAgent", "confidence": 1.0, "linked_to": [title_id], "addedBy": "DocumentAgent"}
        }
    })
    await asyncio.sleep(0.08)

    # Arrow: title → summary
    await broadcast_fn({
        "type": "bind_arrow",
        "payload": {
            "fromShapeId": title_id,
            "toShapeId": summary_id,
            "label": "",
            "color": "grey",
        }
    })
    await asyncio.sleep(0.05)

    # ── 3. Insights row ────────────────────────────────────────────────────
    insights = result.insights[:4]
    insights_y = summary_y + NOTE_H + GAP_V

    # Center the row
    total_insights_w = len(insights) * INSIGHT_W + (len(insights) - 1) * GAP_H
    insights_start_x = base_x + (CARD_W - total_insights_w) // 2

    insight_color_map = {"high": "violet", "medium": "blue", "low": "light-blue"}
    insight_ids = []

    for i, insight in enumerate(insights):
        ix = insights_start_x + i * (INSIGHT_W + GAP_H)
        color = insight_color_map.get(insight.importance, "blue")
        insight_id = _make_id(f"doc_insight_{i}")
        insight_ids.append(insight_id)

        await broadcast_fn({
            "type": "add_geo",
            "payload": {
                "id": insight_id,
                "x": ix,
                "y": insights_y,
                "w": INSIGHT_W,
                "h": INSIGHT_H,
                "text": f"{insight.title}\n\n{insight.content}",
                "geo": "rectangle",
                "color": color,
                "fill": "semi",
                "meta": {"semanticRole": "document_insight", "source": "DocumentAgent", "confidence": 0.85, "linked_to": [summary_id], "addedBy": "DocumentAgent"}
            }
        })
        await asyncio.sleep(0.06)

        # Arrow: summary → insight
        await broadcast_fn({
            "type": "bind_arrow",
            "payload": {
                "fromShapeId": summary_id,
                "toShapeId": insight_id,
                "label": "",
                "color": "grey",
            }
        })
        await asyncio.sleep(0.04)

    # ── 4. Provocation questions (violet sticky notes) ─────────────────────
    questions = result.key_questions[:2]
    if questions:
        questions_y = insights_y + INSIGHT_H + GAP_V
        q_total_w = len(questions) * NOTE_W + (len(questions) - 1) * GAP_H
        q_start_x = base_x + (CARD_W - q_total_w) // 2

        for i, question in enumerate(questions):
            qx = q_start_x + i * (NOTE_W + GAP_H)
            q_id = _make_id(f"doc_question_{i}")
            await broadcast_fn({
                "type": "add_note",
                "payload": {
                    "id": q_id,
                    "x": qx,
                    "y": questions_y,
                    "text": question if question.endswith("?") else question + "?",
                    "color": "light-violet",
                    "size": "s",
                    "meta": {"semanticRole": "provocation", "source": "DocumentAgent", "confidence": 0.75, "linked_to": insight_ids, "addedBy": "DocumentAgent"}
                }
            })
            await asyncio.sleep(0.06)

    # Focus on the cluster
    await broadcast_fn({
        "type": "focus_artifact",
        "payload": {
            "shapeIds": [title_id, summary_id] + insight_ids,
            "primaryShapeId": title_id,
            "reason": "document_ready",
        }
    })

    print(f"[DocumentAgent] Think Mode — '{filename}' map placed: {len(insights)} insights, {len(questions)} provocations.")


# ── ADK analysis ──────────────────────────────────────────────────────────────

async def _analyze_document(filename: str, text: str, query: str) -> Optional[DocumentResult]:
    try:
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="alphasurface", user_id="user", session_id="document_session"
        )

        agent = Agent(
            name="document_analyzer",
            model=_MODEL,
            instruction=(
                f"You are a document analysis specialist. Analyze the text from '{filename}'.\n\n"
                f"User request: {query}\n\n"
                f"Document text:\n{text}"
            ),
            output_schema=DocumentResult,
            output_key="doc_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=types.GenerateContentConfig(temperature=0),
        )

        runner = Runner(agent=agent, app_name="alphasurface", session_service=session_service)
        message = types.Content(role="user", parts=[types.Part(text=f"Analyze: {filename}")])

        async for _ in runner.run_async(user_id="user", session_id="document_session", new_message=message):
            pass

        session = await session_service.get_session(
            app_name="alphasurface", user_id="user", session_id="document_session"
        )
        if not session or "doc_result" not in session.state:
            return None

        return DocumentResult(**session.state["doc_result"])
    except Exception as e:
        print(f"[DocumentAgent] Analysis error: {e}")
        return None


# ── Main handler ──────────────────────────────────────────────────────────────

async def run_document(payload: dict, broadcast_fn) -> None:
    """
    Main handler. Called by dispatcher.
    payload = {'query': str, 'mode': 'think' | 'explain'}
    """
    query = payload.get("query", "").strip()
    mode = payload.get("mode", "think")

    if not query:
        print("[DocumentAgent] Empty query — skipping")
        return

    print(f"[DocumentAgent] Processing — mode={mode} query={query}")

    filename = _find_matching_file(query)
    if not filename:
        print(f"[DocumentAgent] No matching file in {DOCS_DIR}")
        return

    filepath = os.path.join(DOCS_DIR, filename)
    text = _extract_text(filepath)

    if not text.strip():
        print(f"[DocumentAgent] No text extracted from {filename}")
        return

    try:
        if mode == "explain":
            # Present Mode: silent, memory only
            await _handle_present_mode(filename, text, broadcast_fn)
        else:
            # Think Mode: full spatial analysis
            result = await _analyze_document(filename, text, query)
            if result is None:
                # Fallback: basic placement without ADK
                print("[DocumentAgent] ADK analysis failed — placing basic note")
                vp = canvas_state.get("viewport", {"x": 0, "y": 0, "w": 1200, "h": 800})
                await broadcast_fn({
                    "type": "add_note",
                    "payload": {
                        "id": _make_id("doc_fallback"),
                        "x": int(vp["x"] + vp["w"] * 0.1),
                        "y": int(vp["y"] + vp["h"] * 0.1),
                        "text": f"📄 {filename}\n\nLoaded — ask me about it.",
                        "color": "blue",
                        "size": "m",
                    }
                })
                return
            await _handle_think_mode(filename, result, broadcast_fn)

    except Exception as e:
        print(f"[DocumentAgent] Error: {e}")
        import traceback
        traceback.print_exc()
        await emit_failure_note(broadcast_fn, "DocumentAgent", e)
