"""
AlphaSurface — ImageGenAgent

Triggered by:
  Live Agent calls dispatch_image_gen("prompt") → task lands in queue

Flow:
  1. Receives {prompt: str} payload from dispatcher
  2. Calls Gemini image generation (gemini-2.5-flash-image / Nano Banana)
  3. Saves PNG to backend/static/images/ — served by FastAPI at /static/images/{id}.png
  4. Broadcasts add_image message → App.jsx places it on canvas
  5. Stamps "🎨 ImageGenAgent" attribution above the image

Frontend requirement:
  App.jsx must handle message type "add_image":
    { type: "add_image", id, x, y, width, height, src }
  where src is a URL like "http://localhost:8000/static/images/{id}.png"
"""

import asyncio
import os
import time
import uuid
from pathlib import Path

from google import genai
from google.genai import types

# ── Config ────────────────────────────────────────────────────────────────────

_MODEL = "gemini-2.5-flash-image"
_STATIC_DIR = Path(__file__).parent.parent / "static" / "images"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Base URL for serving images — override with ALPHASURFACE_BASE_URL env var
_BASE_URL = os.environ.get("ALPHASURFACE_BASE_URL", "http://localhost:8000")


# ── Image generation ──────────────────────────────────────────────────────────

def _generate_image_sync(prompt: str) -> bytes | None:
    """Synchronous image generation — runs in thread with retry on 429."""
    client = genai.Client()

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

            # Look through candidates to safely access parts
            for candidate in response.candidates:
                if not candidate.content or not candidate.content.parts:
                    continue
                for part in candidate.content.parts:
                    if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                        return part.inline_data.data

            return None
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = 20 * (attempt + 1)
                print(f"[ImageGenAgent] Rate limited, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise


# ── Canvas placement ──────────────────────────────────────────────────────────

async def _place_image(broadcast_fn, image_id: str, prompt: str, width: int = 480, height: int = 480):
    """
    Broadcast canvas actions to place a generated image.
    Layout: attribution stamp above, image below.
    """
    import random
    bx = random.randint(-400, 200)
    by = random.randint(-300, 200)

    image_url = f"{_BASE_URL}/static/images/{image_id}.png"

    # 1 — Attribution stamp
    stamp_id = f"img_stamp_{uuid.uuid4().hex[:8]}"
    await broadcast_fn({
        "type": "add_text",
        "payload": {"id": stamp_id, "x": bx, "y": by - 28, "text": "🎨 ImageGenAgent", "size": "s", "color": "violet"},
    })
    await asyncio.sleep(0.05)

    # 2 — Image shape
    img_shape_id = f"img_{image_id}"
    await broadcast_fn({
        "type": "add_image",
        "id": img_shape_id,
        "x": bx,
        "y": by,
        "width": width,
        "height": height,
        "src": image_url,
    })
    await asyncio.sleep(0.1)

    # 3 — Caption note below
    caption_id = f"img_caption_{uuid.uuid4().hex[:8]}"
    short_prompt = prompt[:60] + ("..." if len(prompt) > 60 else "")
    await broadcast_fn({
        "type": "add_note",
        "payload": {"id": caption_id, "x": bx, "y": by + height + 20, "text": short_prompt, "color": "grey", "size": "m"},
    })
    await asyncio.sleep(0.05)

    # 4 — Zoom to fit
    await broadcast_fn({"type": "zoom_to_fit"})
    print(f"[ImageGenAgent] Image placed — {image_url}")


# ── Main handler ──────────────────────────────────────────────────────────────

async def run_image_gen(payload: dict, broadcast_fn) -> None:
    """
    Main handler. Called by dispatcher with payload = {"prompt": str}.
    """
    prompt = payload.get("prompt", "").strip()
    if not prompt:
        print("[ImageGenAgent] Empty prompt — skipping")
        return

    print(f"[ImageGenAgent] Generating: {prompt[:80]}")

    try:
        image_bytes = await asyncio.to_thread(_generate_image_sync, prompt)

        if not image_bytes:
            print("[ImageGenAgent] No image returned from model")
            return

        # Save to static dir
        image_id = uuid.uuid4().hex[:12]
        image_path = _STATIC_DIR / f"{image_id}.png"
        image_path.write_bytes(image_bytes)
        print(f"[ImageGenAgent] Saved {image_path} ({len(image_bytes)} bytes)")

        await _place_image(broadcast_fn, image_id, prompt)

    except Exception as e:
        print(f"[ImageGenAgent] Error: {e}")
        import traceback
        traceback.print_exc()
