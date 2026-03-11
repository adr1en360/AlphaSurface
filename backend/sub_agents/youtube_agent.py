"""
AlphaSurface — YouTubeAgent

Triggered by:
  Live Agent calls dispatch_youtube("topic") → task lands in queue

Flow:
  1. Receives {query: str} payload from dispatcher
  2. Runs ADK Agent with google_search to find top YouTube URLs for the topic
  3. Places each video on canvas as an embed shape (tldraw's YouTube iframe embed)

Canvas layout: videos laid out vertically, staggered slightly so titles don't overlap.
"""

import asyncio
import os
import random
import re
from typing import Optional

from pydantic import BaseModel, Field

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search
from google.genai import types

# ── Config ────────────────────────────────────────────────────────────────────

_MODEL = "gemini-2.5-flash"

_SYSTEM_PROMPT = """\
You are a YouTube research assistant. Your job is to find the best YouTube videos
for a given topic and return structured information so they can be embedded on a canvas.

Rules:
- Use google_search to find real YouTube videos (search for: "<topic> site:youtube.com")
- Return 2-4 of the most relevant, high-quality videos
- Each video MUST have a full youtube.com/watch?v= URL (not shortened links)
- Prefer tutorial, explainer, or documentary content over short clips
- NEVER guess or fabricate video URLs — only return URLs found via search
"""


class YouTubeVideo(BaseModel):
    title: str = Field(description="Short video title (max 8 words)")
    url: str = Field(description="Full YouTube URL: https://www.youtube.com/watch?v=XXXX")
    channel: Optional[str] = Field(description="Channel name, or null if not found")


class YouTubeResult(BaseModel):
    topic: str = Field(description="Short topic label (max 4 words)")
    videos: list[YouTubeVideo] = Field(description="2-4 YouTube videos, best first")


# ── Canvas placement helpers ──────────────────────────────────────────────────

def _canvas_pos():
    """Return a base (x, y) position with slight randomness."""
    base_x = random.randint(-700, 100)
    base_y = random.randint(-400, 200)
    return base_x, base_y


def _make_shape_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _is_valid_youtube_url(url: str) -> bool:
    """Validate that the URL is a real YouTube watch URL."""
    return bool(re.match(r"https?://(www\.)?youtube\.com/watch\?v=[\w-]{11}", url))


async def _place_youtube_cluster(broadcast_fn, topic: str, videos: list[YouTubeVideo]):
    """Broadcast embed shapes for each video, fanned vertically."""
    bx, by = _canvas_pos()
    embed_w, embed_h = 560, 315
    gap = 40

    # Topic label at top
    stamp_id = _make_shape_id("yt_stamp")
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "id": stamp_id,
            "x": bx,
            "y": by - 30,
            "text": f"▶ YouTubeAgent · {topic}",
            "size": "s",
            "color": "red",
        }
    })
    await asyncio.sleep(0.05)

    for i, video in enumerate(videos):
        if not _is_valid_youtube_url(video.url):
            print(f"[YouTubeAgent] Skipping invalid URL: {video.url}")
            continue

        embed_y = by + i * (embed_h + gap)

        # Title text above the embed
        title_id = _make_shape_id(f"yt_title_{i}")
        await broadcast_fn({
            "type": "add_text",
            "payload": {
                "id": title_id,
                "x": bx,
                "y": embed_y - 24,
                "text": video.title + (f" · {video.channel}" if video.channel else ""),
                "size": "s",
                "color": "grey",
            }
        })
        await asyncio.sleep(0.05)

        # Embed the YouTube iframe
        embed_id = _make_shape_id(f"yt_embed_{i}")
        await broadcast_fn({
            "type": "add_embed",
            "payload": {
                "id": embed_id,
                "x": bx,
                "y": embed_y,
                "url": video.url,
                "w": embed_w,
                "h": embed_h,
            }
        })
        await asyncio.sleep(0.15)

    await broadcast_fn({"type": "zoom_to_fit", "payload": {}})
    print(f"[YouTubeAgent] Placed {len(videos)} video(s) for '{topic}'")


# ── Core logic ────────────────────────────────────────────────────────────────

async def run_youtube(payload: dict, broadcast_fn) -> None:
    """Main handler. Called by dispatcher with payload = {\"query\": str}."""
    query = payload.get("query", "").strip()
    if not query:
        print("[YouTubeAgent] Empty query — skipping")
        return

    print(f"[YouTubeAgent] Finding videos for: {query}")

    try:
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="alphasurface", user_id="user", session_id="youtube_session"
        )

        # Formatter agent (enforces schema, no tools)
        youtube_formatter = Agent(
            name="youtube_formatter",
            model=_MODEL,
            instruction=(
                "Given the raw search results below, extract 2-4 real YouTube videos "
                "matching the topic. Return ONLY real youtube.com/watch?v= URLs found "
                "in the search results. Do NOT invent video IDs.\n\nSearch results:\n{raw_videos}"
            ),
            output_schema=YouTubeResult,
            output_key="youtube_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=types.GenerateContentConfig(temperature=0),
        )

        # Fetcher agent (uses google_search, saves output to raw_videos in session state)
        youtube_fetcher = Agent(
            name="youtube_fetcher",
            model=_MODEL,
            instruction=_SYSTEM_PROMPT,
            tools=[google_search],
            output_key="raw_videos",
            generate_content_config=types.GenerateContentConfig(temperature=0.1),
        )

        from google.adk.agents import SequentialAgent

        pipeline = SequentialAgent(
            name="youtube_pipeline",
            sub_agents=[youtube_fetcher, youtube_formatter],
        )

        runner = Runner(
            agent=pipeline,
            app_name="alphasurface",
            session_service=session_service,
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=f"Find the best YouTube videos about: {query}")]
        )

        async for event in runner.run_async(
            user_id="user", session_id="youtube_session", new_message=message
        ):
            if event.is_final_response():
                pass

        session = await session_service.get_session(
            app_name="alphasurface", user_id="user", session_id="youtube_session"
        )
        if not session or "youtube_result" not in session.state:
            print("[YouTubeAgent] Failed to retrieve valid schema response.")
            return

        result: dict = session.state["youtube_result"]
        topic = result.get("topic", query[:30])
        raw_videos = result.get("videos", [])

        videos = [
            YouTubeVideo(
                title=v.get("title", "Video"),
                url=v.get("url", ""),
                channel=v.get("channel"),
            )
            for v in raw_videos
            if isinstance(v, dict) and _is_valid_youtube_url(v.get("url", ""))
        ]

        if not videos:
            print("[YouTubeAgent] No valid YouTube URLs returned — skipping canvas placement.")
            return

        await _place_youtube_cluster(broadcast_fn, topic, videos)

    except Exception as e:
        print(f"[YouTubeAgent] Error: {e}")
        import traceback
        traceback.print_exc()
