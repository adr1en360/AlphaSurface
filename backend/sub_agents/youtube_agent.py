"""
AlphaSurface — YouTubeAgent (Hybrid: Gemini + YouTube Data API v3)

Flow:
  1. Gemini optimizes the user query into the best YouTube search string
  2. YouTube Data API v3 returns real video IDs + duration metadata
  3. Duration filter: skips livestreams and very long videos (>90 min)
  4. Places the best 1-3 videos on canvas as embed shapes (playable iframe)

Requires: YOUTUBE_API_KEY in .env
"""

import asyncio
import os
import re
import time
from typing import Optional

from googleapiclient.discovery import build
from google.genai import Client
from model_config import FAST_MODEL
from sub_agents import emit_failure_note
from tools.state import canvas_state

# ── Config ────────────────────────────────────────────────────────────────────

_MODEL = FAST_MODEL
_MAX_RESULTS = 5          # candidates to fetch from YouTube API
_MAX_DURATION_SECS = 5400  # 90 minutes — skip anything longer (livestream/movie)
_MIN_DURATION_SECS = 60    # 1 minute — skip very short clips
_RECENT_VIDEO_TTL_SECS = 600
_recent_video_ids: dict[str, float] = {}

# ── YouTube API client ────────────────────────────────────────────────────────

def _get_youtube_client():
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key or api_key == "YOUR_YOUTUBE_API_KEY_HERE":
        return None
    return build("youtube", "v3", developerKey=api_key)


def _parse_iso8601_duration(iso: str) -> int:
    """
    Parse YouTube ISO 8601 duration string like PT1H23M45S → seconds.
    Returns -1 for livestreams (which have no duration).
    """
    if not iso or iso == "P0D":
        return -1  # live stream
    pattern = r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
    m = re.match(pattern, iso)
    if not m:
        return -1
    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    seconds = int(m.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _format_duration(secs: int) -> str:
    """Return human-readable duration like '12:34' or '1:23:45'."""
    if secs < 0:
        return "LIVE"
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ── Query optimisation via Gemini ─────────────────────────────────────────────

_gemini_client: Optional[Client] = None

def _get_gemini_client() -> Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = Client(api_key=os.getenv("GEMINI_API_KEY", ""))
    return _gemini_client


async def _optimise_query(user_query: str) -> str:
    """
    Use Gemini to turn a conversational request into the best YouTube search string.
    E.g. "show me quantum teleportation" → "quantum teleportation explained science"
    """
    try:
        client = _get_gemini_client()
        system = (
            "You are a YouTube search specialist. "
            "Turn the user's request into the single best YouTube search query. "
            "Focus on educational, tutorial, or documentary content. "
            "Return ONLY the search query string — no punctuation, no explanation."
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=_MODEL,
            contents=[user_query],
            config={"system_instruction": system},
        )
        optimised = response.text.strip().strip('"')
        print(f"[YouTubeAgent] Optimised query: {optimised!r}")
        return optimised
    except Exception as e:
        print(f"[YouTubeAgent] Query optimisation failed ({e}), using raw query")
        return user_query


# ── YouTube API search + filter ───────────────────────────────────────────────

async def _search_youtube(query: str) -> list[dict]:
    """
    Search YouTube API, fetch durations, filter out livestreams and
    very long or very short videos. Returns list of video dicts.
    """
    yt = _get_youtube_client()
    if not yt:
        print("[YouTubeAgent] YOUTUBE_API_KEY not set — cannot search.")
        return []

    try:
        # Step 1: search
        search_req = yt.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=_MAX_RESULTS,
            relevanceLanguage="en",
            safeSearch="moderate",
        )
        search_res = await asyncio.to_thread(search_req.execute)
        items = search_res.get("items", [])

        if not items:
            return []

        # Step 2: fetch durations via videos.list
        video_ids = [item["id"]["videoId"] for item in items]
        detail_req = yt.videos().list(
            id=",".join(video_ids),
            part="contentDetails,snippet,status",
        )
        detail_res = await asyncio.to_thread(detail_req.execute)
        details = {v["id"]: v for v in detail_res.get("items", [])}

        # Step 3: build + filter results
        videos = []
        for item in items:
            vid_id = item["id"]["videoId"]
            detail = details.get(vid_id, {})
            content = detail.get("contentDetails", {})
            status = detail.get("status", {})
            snippet = item["snippet"]

            duration_iso = content.get("duration", "")
            duration_secs = _parse_iso8601_duration(duration_iso)

            # Skip livestreams and out-of-range durations
            if duration_secs < 0:
                print(f"[YouTubeAgent] Skipping livestream: {snippet['title']}")
                continue
            if duration_secs < _MIN_DURATION_SECS:
                print(f"[YouTubeAgent] Skipping too-short ({duration_secs}s): {snippet['title']}")
                continue
            if duration_secs > _MAX_DURATION_SECS:
                print(f"[YouTubeAgent] Skipping too-long ({_format_duration(duration_secs)}): {snippet['title']}")
                continue

            # Skip videos that cannot be embedded in iframe.
            if status.get("embeddable") is False:
                print(f"[YouTubeAgent] Skipping non-embeddable: {snippet['title']}")
                continue

            videos.append({
                "video_id": vid_id,
                "title": snippet["title"],
                "channel": snippet["channelTitle"],
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "duration_secs": duration_secs,
                "duration_label": _format_duration(duration_secs),
            })

        return videos

    except Exception as e:
        print(f"[YouTubeAgent] YouTube API error: {e}")
        import traceback
        traceback.print_exc()
        return []


# ── Canvas placement ──────────────────────────────────────────────────────────

def _existing_canvas_video_ids() -> set[str]:
    ids: set[str] = set()
    for s in canvas_state.get("shapes", []):
        if not isinstance(s, dict):
            continue
        if s.get("type") != "embed":
            continue
        url = str(s.get("url", ""))
        m = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", url)
        if m:
            ids.add(m.group(1))
    return ids


def _prune_recent_video_ids(now: float) -> None:
    stale = [vid for vid, ts in _recent_video_ids.items() if (now - ts) > _RECENT_VIDEO_TTL_SECS]
    for vid in stale:
        _recent_video_ids.pop(vid, None)


def _filter_new_videos(videos: list[dict]) -> list[dict]:
    now = time.monotonic()
    _prune_recent_video_ids(now)
    existing_ids = _existing_canvas_video_ids()
    fresh: list[dict] = []
    seen_in_batch: set[str] = set()
    for video in videos:
        vid = str(video.get("video_id", ""))
        if not vid:
            continue
        if vid in existing_ids:
            continue
        if vid in _recent_video_ids:
            continue
        if vid in seen_in_batch:
            continue
        fresh.append(video)
        seen_in_batch.add(vid)
    return fresh

def _find_empty_video_origin(stack_w: int, stack_h: int) -> tuple[int, int]:
    vp = canvas_state.get("viewport", {"x": 0, "y": 0, "w": 1200, "h": 800})
    shapes = canvas_state.get("shapes", [])

    cx = int(vp["x"] + vp["w"] * 0.62)
    cy = int(vp["y"] + vp["h"] * 0.08)

    def overlaps(px: int, py: int) -> bool:
        pad = 64
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
            (ring * 640, 0),
            (0, ring * 360),
            (-ring * 640, 0),
            (0, -ring * 360),
            (ring * 640, ring * 360),
            (-ring * 640, ring * 360),
            (ring * 640, -ring * 360),
            (-ring * 640, -ring * 360),
        ]:
            tx, ty = cx + dx, cy + dy
            if not overlaps(tx, ty):
                return tx, ty

    return cx + 740, cy + 420


def _make_shape_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _place_videos(broadcast_fn, query: str, videos: list[dict]):
    """Place each video as an iframe embed with a title label above it."""
    embed_w, embed_h = 560, 315
    title_h = 40    # height reserved for title text above each embed
    gap = 60        # gap between bottom of one embed and title of next
    slot_h = title_h + embed_h + gap
    stack_h = len(videos) * slot_h + 60
    bx, by = _find_empty_video_origin(embed_w + 40, stack_h)

    # Stamp label at top
    stamp_id = _make_shape_id("yt_stamp")
    await broadcast_fn({
        "type": "add_text",
        "payload": {
            "id": stamp_id,
            "x": bx,
            "y": by,
            "text": f"▶ YouTubeAgent · {query}",
            "size": "s",
            "color": "red",
        }
    })
    await asyncio.sleep(0.05)

    for i, video in enumerate(videos):
        slot_y = by + 40 + i * slot_h  # 40px clearance below stamp

        # Title above embed
        title_id = _make_shape_id(f"yt_title_{i}")
        await broadcast_fn({
            "type": "add_text",
            "payload": {
                "id": title_id,
                "x": bx,
                "y": slot_y,
                "text": f"{video['title']}  [{video['duration_label']}]  · {video['channel']}",
                "size": "s",
                "color": "grey",
            }
        })
        await asyncio.sleep(0.05)

        # Embed below title
        embed_id = _make_shape_id(f"yt_embed_{i}")
        await broadcast_fn({
            "type": "add_embed",
            "payload": {
                "id": embed_id,
                "x": bx,
                "y": slot_y + title_h,
                "url": video["url"],
                "w": embed_w,
                "h": embed_h,
            }
        })
        await asyncio.sleep(0.15)

    now = time.monotonic()
    for video in videos:
        vid = str(video.get("video_id", ""))
        if vid:
            _recent_video_ids[vid] = now
    print(f"[YouTubeAgent] Placed {len(videos)} video(s) for '{query}'")


# ── Main handler ──────────────────────────────────────────────────────────────

async def run_youtube(payload: dict, broadcast_fn) -> None:
    """Main handler. Called by dispatcher with payload = {'query': str}."""
    query = payload.get("query", "").strip()
    requested_count = payload.get("count", payload.get("max_results"))
    if requested_count is None:
        q = query.lower()
        m = re.search(r"\b([1-5])\s*(?:video|videos)\b", q)
        if m:
            requested_count = int(m.group(1))
        else:
            word_to_num = {
                "one": 1,
                "two": 2,
                "three": 3,
                "four": 4,
                "five": 5,
                "a": 1,
                "an": 1,
                "single": 1,
                "couple": 2,
            }
            word_match = re.search(
                r"\b(one|two|three|four|five|a|an|single|couple)\s*(?:video|videos)\b",
                q,
            )
            requested_count = word_to_num.get(word_match.group(1), 3) if word_match else 3
    try:
        requested_count = int(requested_count)
    except Exception:
        requested_count = 3
    requested_count = max(1, min(requested_count, 5))
    if not query:
        print("[YouTubeAgent] Empty query — skipping")
        return

    print(f"[YouTubeAgent] Finding videos for: {query}")

    try:
        # 1. Gemini optimises the search query
        search_query = await _optimise_query(query)

        # 2. YouTube API returns real videos with duration metadata
        videos = await _search_youtube(search_query)
        videos = _filter_new_videos(videos)
        videos = videos[:requested_count]

        if not videos:
            print("[YouTubeAgent] No suitable videos found — skipping canvas placement.")
            return

        # 3. Place on canvas
        await _place_videos(broadcast_fn, query, videos)

    except Exception as e:
        print(f"[YouTubeAgent] Error: {e}")
        import traceback
        traceback.print_exc()
        await emit_failure_note(broadcast_fn, "YouTubeAgent", e)