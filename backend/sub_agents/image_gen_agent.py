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
import httpx
import os
import textwrap
import time
import uuid
from urllib.parse import quote_plus
from pathlib import Path

from google import genai
from google.genai import types
from model_config import IMAGE_MODEL
from sub_agents import emit_failure_note
from tools.state import canvas_state

# ── Config ────────────────────────────────────────────────────────────────────

_MODEL = IMAGE_MODEL
_STATIC_DIR = Path(__file__).parent.parent / "static" / "images"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
_IMAGE_PROVIDER = os.environ.get("ALPHASURFACE_IMAGE_PROVIDER", "gemini").strip().lower()
_POLLINATIONS_URL_TEMPLATE = os.environ.get(
    "POLLINATIONS_IMAGE_URL_TEMPLATE",
    "https://gen.pollinations.ai/image/{prompt}",
)
_POLLINATIONS_MODEL = os.environ.get("POLLINATIONS_IMAGE_MODEL", "flux")
_POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "").strip()

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


def _generate_image_pollinations_sync(prompt: str) -> bytes | None:
    encoded_prompt = quote_plus(prompt)
    template = _POLLINATIONS_URL_TEMPLATE.strip()
    # Normalize legacy templates to the current API host/path.
    template = template.replace("https://image.pollinations.ai/prompt/", "https://gen.pollinations.ai/image/")
    template = template.replace("https://image.pollinations.ai/image/", "https://gen.pollinations.ai/image/")
    url = template.format(prompt=encoded_prompt)
    headers = {}
    if _POLLINATIONS_API_KEY:
        # Some Pollinations-compatible gateways use bearer auth.
        headers["Authorization"] = f"Bearer {_POLLINATIONS_API_KEY}"

    params = {
        "model": _POLLINATIONS_MODEL,
        "width": 1024,
        "height": 1024,
        "nologo": "true",
    }
    if _POLLINATIONS_API_KEY:
        params["key"] = _POLLINATIONS_API_KEY

    candidates = [url]

    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        last_exc: Exception | None = None
        for endpoint in candidates:
            for attempt in range(2):
                try:
                    response = client.get(endpoint, headers=headers, params=params)
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if "image" not in content_type and not response.content:
                        return None
                    return response.content
                except Exception as exc:
                    last_exc = exc
                    status_code = getattr(getattr(exc, "response", None), "status_code", None)
                    if status_code == 401 and not _POLLINATIONS_API_KEY:
                        raise RuntimeError(
                            "Pollinations rejected the request with 401. "
                            "Set POLLINATIONS_API_KEY to enable Pollinations fallback."
                        ) from exc
                    if attempt == 0:
                        time.sleep(1.2)
                        continue
        if last_exc:
            raise last_exc
        return None


def _generate_image_with_provider_sync(prompt: str) -> bytes | None:
    provider = _IMAGE_PROVIDER
    if provider == "pollinations":
        return _generate_image_pollinations_sync(prompt)

    try:
        return _generate_image_sync(prompt)
    except Exception as e:
        msg = str(e)
        is_rate_limited = "429" in msg or "RESOURCE_EXHAUSTED" in msg
        if provider == "auto" and is_rate_limited:
            if not _POLLINATIONS_API_KEY:
                raise RuntimeError(
                    "429 RESOURCE_EXHAUSTED from Gemini and Pollinations fallback is unavailable. "
                    "Set POLLINATIONS_API_KEY or switch ALPHASURFACE_IMAGE_PROVIDER to gemini."
                ) from e
            print("[ImageGenAgent] Gemini rate-limited, falling back to Pollinations")
            return _generate_image_pollinations_sync(prompt)
        raise


# ── Canvas placement ──────────────────────────────────────────────────────────

def _find_empty_image_origin(stack_w: int, stack_h: int) -> tuple[int, int]:
    vp = canvas_state.get("viewport", {"x": 0, "y": 0, "w": 1200, "h": 800})
    shapes = canvas_state.get("shapes", [])

    # Place near the visible center-right area so new image joins the active cluster.
    cx = int(vp["x"] + vp["w"] * 0.55)
    cy = int(vp["y"] + vp["h"] * 0.25)

    def overlaps(px: int, py: int) -> bool:
        pad = 36
        for s in shapes:
            if not isinstance(s, dict):
                continue
            sx = int(s.get("x", 0))
            sy = int(s.get("y", 0))
            sw = int(s.get("w", 220))
            sh = int(s.get("h", 120))
            if (
                px < sx + sw + pad
                and px + stack_w > sx - pad
                and py < sy + sh + pad
                and py + stack_h > sy - pad
            ):
                return True
        return False

    if not overlaps(cx, cy):
        return cx, cy

    for ring in range(1, 10):
        for dx, dy in [
            (ring * 560, 0),
            (0, ring * 360),
            (-ring * 560, 0),
            (0, -ring * 360),
            (ring * 560, ring * 360),
            (-ring * 560, ring * 360),
            (ring * 560, -ring * 360),
            (-ring * 560, -ring * 360),
        ]:
            tx, ty = cx + dx, cy + dy
            if not overlaps(tx, ty):
                return tx, ty

    return cx, cy

async def _place_image(broadcast_fn, image_id: str, prompt: str, width: int = 480, height: int = 480):
    """
    Broadcast canvas actions to place a generated image.
    Layout: attribution stamp above, image below.
    """
    stack_h = height + 170
    bx, by = _find_empty_image_origin(width, stack_h)

    image_url = f"{_BASE_URL}/static/images/{image_id}.png"

    # 1 — Attribution stamp
    stamp_id = f"shape:img_stamp_{uuid.uuid4().hex[:8]}"
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "id": stamp_id,
            "x": bx,
            "y": by - 28,
            "text": "ImageGenAgent",
            "size": "s",
            "color": "violet",
            "meta": {
                "semanticRole": "image_stamp",
                "source": "ImageGenAgent",
                "confidence": 0.95,
                "linked_to": [f"shape:{image_id}"],
                "addedBy": "ImageGenAgent",
            },
        },
    })
    await asyncio.sleep(0.05)

    # 2 — Image shape
    img_shape_id = f"shape:{image_id}"
    await broadcast_fn({
        "type": "add_image",
        "id": img_shape_id,
        "x": bx,
        "y": by,
        "width": width,
        "height": height,
        "src": image_url,
        "meta": {
            "semanticRole": "generated_image",
            "source": "ImageGenAgent",
            "confidence": 0.9,
            "linked_to": [],
            "addedBy": "ImageGenAgent",
        },
    })
    await asyncio.sleep(0.1)

    # 3 — Multiline prompt details below the image
    caption_id = f"shape:img_caption_{uuid.uuid4().hex[:8]}"
    wrapped_prompt = textwrap.fill(prompt.strip(), width=46) if prompt.strip() else "No prompt provided"
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "id": caption_id,
            "x": bx,
            "y": by + height + 20,
            "text": f"Prompt\n{wrapped_prompt}",
            "color": "black",
            "size": "s",
            "meta": {
                "semanticRole": "image_caption",
                "source": "ImageGenAgent",
                "confidence": 0.8,
                "linked_to": [img_shape_id],
                "addedBy": "ImageGenAgent",
            },
        },
    })
    await asyncio.sleep(0.05)

    # 4 — Viewport-aware focus event
    await broadcast_fn({
        "type": "focus_artifact",
        "payload": {
            "shapeIds": [img_shape_id, caption_id],
            "primaryShapeId": img_shape_id,
            "reason": "image_ready",
        },
    })
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
        image_bytes = await asyncio.to_thread(_generate_image_with_provider_sync, prompt)

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
        msg = str(e)
        is_rate_limited = "429" in msg or "RESOURCE_EXHAUSTED" in msg
        if not is_rate_limited:
            import traceback
            traceback.print_exc()
        await emit_failure_note(broadcast_fn, "ImageGenAgent", e)
