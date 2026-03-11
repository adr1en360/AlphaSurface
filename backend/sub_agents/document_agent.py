"""
AlphaSurface — DocumentAgent

Triggered by:
  Live Agent calls dispatch_document("query") → task lands in queue

Flow:
  1. Scans backend/documents/ for files matching the query
  2. Extracts text from PDF (PyMuPDF) or Docx (python-docx)
  3. Uses ADK Agent to extract key insights, contradictions, and data points
  4. Places formatted results on the canvas

Requires: pymupdf, python-docx
"""

import asyncio
import os
import random
import re
from typing import Optional, List

import fitz  # PyMuPDF
from docx import Document
from pydantic import BaseModel, Field

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# ── Config ────────────────────────────────────────────────────────────────────

_MODEL = "gemini-2.5-flash"
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "documents")

# ── Extraction Helpers ────────────────────────────────────────────────────────

def _extract_text_from_pdf(filepath: str, max_chars: int = 20000) -> str:
    """Extract first few pages of text from a PDF."""
    text = ""
    try:
        with fitz.open(filepath) as doc:
            for page in doc:
                text += page.get_text()
                if len(text) > max_chars:
                    break
    except Exception as e:
        print(f"[DocumentAgent] PDF extraction error: {e}")
    return text[:max_chars]


def _extract_text_from_docx(filepath: str, max_chars: int = 20000) -> str:
    """Extract text from a Word document."""
    text = ""
    try:
        doc = Document(filepath)
        for para in doc.paragraphs:
            text += para.text + "\n"
            if len(text) > max_chars:
                break
    except Exception as e:
        print(f"[DocumentAgent] Docx extraction error: {e}")
    return text[:max_chars]


def _find_matching_file(query: str) -> Optional[str]:
    """Find the best matching file in the documents directory."""
    if not os.path.exists(DOCS_DIR):
        return None
    
    files = os.listdir(DOCS_DIR)
    if not files:
        return None

    # Try to find an exact or fuzzy match
    query_lower = query.lower()
    for f in files:
        if f.lower() in query_lower or query_lower in f.lower():
            return f
    
    # Otherwise, pick the most recent if it's a general request
    # For now, just pick the first one as a fallback if query is broad
    return files[0]


# ── ADK Schemas ───────────────────────────────────────────────────────────────

class DocumentInsight(BaseModel):
    title: str = Field(description="Short title for the insight (max 5 words)")
    content: str = Field(description="Detailed insight or data point (max 15 words)")
    importance: str = Field(description="high, medium, or low")


class DocumentResult(BaseModel):
    filename: str = Field(description="The name of the file processed")
    summary: str = Field(description="One sentence summary of the whole document")
    insights: List[DocumentInsight] = Field(description="Top 3-5 insights extracted from the text")


# ── Canvas Helpers ──────────────────────────────────────────────────────────

def _make_shape_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _canvas_pos():
    return random.randint(-500, 500), random.randint(-400, 400)


async def _place_document_cluster(broadcast_fn, result: DocumentResult):
    """Place a structured cluster of insights on the canvas."""
    bx, by = _canvas_pos()
    
    # Header Note (the summary)
    header_id = _make_shape_id("doc_header")
    await broadcast_fn({
        "type": "add_note",
        "payload": {
            "id": header_id,
            "x": bx,
            "y": by,
            "text": f"📄 **{result.filename}**\n\n{result.summary}",
            "color": "blue",
        }
    })
    await asyncio.sleep(0.1)

    # Insight geo shapes radiating around the header
    angles = [0, 45, -45, 90, -90, 135, -135, 180]
    radius = 350
    
    for i, insight in enumerate(result.insights[:4]):
        angle = angles[i % len(angles)]
        import math
        rad = math.radians(angle)
        offset_x = radius * math.cos(rad)
        offset_y = radius * math.sin(rad)
        
        insight_id = _make_shape_id(f"doc_insight_{i}")
        color = "light-blue" if insight.importance == "low" else ("blue" if insight.importance == "medium" else "violet")
        
        await broadcast_fn({
            "type": "add_geo",
            "payload": {
                "id": insight_id,
                "x": bx + offset_x,
                "y": by + offset_y,
                "w": 300,
                "h": 100,
                "text": f"**{insight.title}**\n{insight.content}",
                "color": color,
                "geo": "rectangle",
            }
        })
        await asyncio.sleep(0.05)
        
        # Connection arrow
        arrow_id = _make_shape_id(f"doc_arrow_{i}")
        await broadcast_fn({
            "type": "add_arrow",
            "payload": {
                "id": arrow_id,
                "x": bx + 100,
                "y": by + 100,
                "label": "",
                "color": "grey",
                "start": {"x": 50, "y": 50},
                "end": {"x": 150, "y": 150},
            }
        })
        await asyncio.sleep(0.05)
        
        # Bind arrow
        await broadcast_fn({
            "type": "bind_arrow",
            "payload": {
                "id": arrow_id,
                "fromId": header_id,
                "toId": insight_id,
            }
        })
        await asyncio.sleep(0.05)

    await broadcast_fn({"type": "zoom_to_fit", "payload": {}})


# ── Main Handler ──────────────────────────────────────────────────────────────

async def run_document(payload: dict, broadcast_fn) -> None:
    """Main handler. Called by dispatcher with payload = {'query': str}."""
    query = payload.get("query", "").strip()
    if not query:
        print("[DocumentAgent] Empty query — skipping")
        return

    print(f"[DocumentAgent] Processing request: {query}")

    filename = _find_matching_file(query)
    if not filename:
        print(f"[DocumentAgent] No matching file found in {DOCS_DIR}")
        return
    
    filepath = os.path.join(DOCS_DIR, filename)
    print(f"[DocumentAgent] Reading file: {filename}")

    # Extract text
    if filename.lower().endswith(".pdf"):
        text = _extract_text_from_pdf(filepath)
    elif filename.lower().endswith(".docx"):
        text = _extract_text_from_docx(filepath)
    elif filename.lower().endswith(".txt"):
        with open(filepath, "r") as f:
            text = f.read()
    else:
        print(f"[DocumentAgent] Unsupported file type: {filename}")
        return

    if not text.strip():
        print(f"[DocumentAgent] No text extracted from {filename}")
        return

    try:
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="alphasurface", user_id="user", session_id="document_session"
        )

        agent = Agent(
            name="document_analyzer",
            model=_MODEL,
            instruction=(
                f"You are a document analysis specialist. Analyze the following text extracted from '{filename}'. "
                "Focus on extracting the core insights and data points requested if any. "
                "If no specific request was made, give a general overview.\n\n"
                f"User request: {query}\n\n"
                f"Document text:\n{text}"
            ),
            output_schema=DocumentResult,
            output_key="doc_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=types.GenerateContentConfig(temperature=0),
        )

        runner = Runner(
            agent=agent,
            app_name="alphasurface",
            session_service=session_service,
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=f"Analyze this document: {filename}")]
        )

        async for event in runner.run_async(
            user_id="user", session_id="document_session", new_message=message
        ):
            if event.is_final_response():
                pass

        session = await session_service.get_session(
            app_name="alphasurface", user_id="user", session_id="document_session"
        )
        if not session or "doc_result" not in session.state:
            print("[DocumentAgent] Failed to retrieve valid schema response.")
            return

        result_data = session.state["doc_result"]
        # Ensure it matches our model
        result = DocumentResult(**result_data)
        
        await _place_document_cluster(broadcast_fn, result)
        print(f"[DocumentAgent] Successfully placed cluster for {filename}")

    except Exception as e:
        print(f"[DocumentAgent] Error: {e}")
        import traceback
        traceback.print_exc()
