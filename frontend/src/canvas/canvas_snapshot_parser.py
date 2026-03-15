# ── canvas_snapshot_parser.py ─────────────────────────────────────────────────
# Converts the three-tier canvas snapshot from the frontend into a
# human-readable string that gets injected into Gemini's context.
# Drop this file into your AlphaSurface Python folder.
# Import it in live_session.py: from canvas_snapshot_parser import format_snapshot_for_gemini

def format_snapshot_for_gemini(snapshot: dict) -> str:
    """
    Converts the three-tier canvas snapshot into a clear context string for Gemini.

    Tiers:
      blurryShapes       — shapes in viewport (light: id, type, pos, text)
      focusedShapes      — selected/agent shapes (full: color, fill, etc.)
      peripheralClusters — shapes outside viewport (grouped: count + bounds)
    """
    payload = snapshot.get("payload", snapshot)
    lines = []

    # ── Viewport info ──────────────────────────────────────────────────────
    vp = payload.get("viewport", {})
    if vp:
        lines.append(
            f"Viewport: x={vp.get('x',0)} y={vp.get('y',0)} "
            f"w={vp.get('w',1200)} h={vp.get('h',800)} zoom={vp.get('zoom',1):.2f}"
        )

    page_name = payload.get("currentPageName", "")
    shape_count = payload.get("shape_count", 0)
    lines.append(f"Page: '{page_name}' | Total shapes: {shape_count}")

    # ── Selected shapes ────────────────────────────────────────────────────
    selected = payload.get("selectedShapeIds", [])
    if selected:
        lines.append(f"Selected: {', '.join(selected)}")

    # ── TIER 2: Focused shapes (selected / agent-placed — full detail) ─────
    focused = payload.get("focusedShapes", [])
    if focused:
        lines.append(f"\n--- FOCUSED SHAPES ({len(focused)} — full detail) ---")
        for s in focused:
            shape_type = s.get("_type", s.get("type", "unknown"))
            sid = s.get("shapeId", "?")
            text = s.get("text", "")
            color = s.get("color", "")
            fill = s.get("fill", "")
            x, y = s.get("x", 0), s.get("y", 0)
            w, h = s.get("w", ""), s.get("h", "")

            parts = [f"[{shape_type}] id={sid} at ({x},{y})"]
            if w and h: parts.append(f"size={w}x{h}")
            if color: parts.append(f"color={color}")
            if fill: parts.append(f"fill={fill}")
            if text: parts.append(f'text="{text[:80]}"')

            # Arrow-specific
            if shape_type == "arrow":
                from_id = s.get("fromId")
                to_id = s.get("toId")
                if from_id or to_id:
                    parts.append(f"from={from_id} → to={to_id}")

            lines.append("  " + " | ".join(parts))

    # ── TIER 1: Blurry shapes (visible in viewport — lightweight) ─────────
    blurry = payload.get("blurryShapes", [])
    if blurry:
        lines.append(f"\n--- VIEWPORT SHAPES ({len(blurry)} visible — overview) ---")
        for s in blurry:
            shape_type = s.get("type", "unknown")
            sid = s.get("shapeId", "?")
            x, y, w, h = s.get("x", 0), s.get("y", 0), s.get("w", 0), s.get("h", 0)
            text = s.get("text", "")
            line = f"  [{shape_type}] id={sid} at ({x},{y}) size={w}x{h}"
            if text: line += f' "{text[:60]}"'
            lines.append(line)

    # ── TIER 3: Peripheral clusters (outside viewport — grouped) ──────────
    clusters = payload.get("peripheralClusters", [])
    if clusters:
        lines.append(f"\n--- OFF-SCREEN CLUSTERS ({len(clusters)} groups) ---")
        for c in clusters:
            b = c.get("bounds", {})
            count = c.get("numberOfShapes", 0)
            lines.append(
                f"  {count} shape(s) at x={b.get('x',0)} y={b.get('y',0)} "
                f"w={b.get('w',0)} h={b.get('h',0)}"
            )

    return "\n".join(lines)
