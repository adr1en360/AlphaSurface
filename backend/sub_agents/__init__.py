import asyncio
from tools.state import canvas_state


def find_empty_note_position(note_w: int = 320, note_h: int = 140) -> tuple[int, int]:
	"""Pick a note position that avoids existing canvas shapes when possible."""
	vp = canvas_state.get("viewport", {"x": 0, "y": 0, "w": 1200, "h": 800})
	shapes = canvas_state.get("shapes", [])

	base_x = int(vp["x"] + vp["w"] * 0.08)
	base_y = int(vp["y"] + vp["h"] * 0.08)

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
				and px + note_w > sx - pad
				and py < sy + sh + pad
				and py + note_h > sy - pad
			):
				return True
		return False

	if not overlaps(base_x, base_y):
		return base_x, base_y

	for ring in range(1, 10):
		for dx, dy in [
			(ring * 360, 0),
			(0, ring * 220),
			(-ring * 360, 0),
			(0, -ring * 220),
			(ring * 360, ring * 220),
			(-ring * 360, ring * 220),
			(ring * 360, -ring * 220),
			(-ring * 360, -ring * 220),
		]:
			tx, ty = base_x + dx, base_y + dy
			if not overlaps(tx, ty):
				return tx, ty

	return base_x + 420, base_y + 260


async def emit_failure_note(broadcast_fn, agent_name: str, error: Exception | str) -> None:
	"""Broadcast a visible canvas note when a sub-agent fails."""
	message = str(error).strip() if error is not None else "unknown error"
	lower = message.lower()
	if "resource_exhausted" in lower or "429" in lower or "rate" in lower:
		user_text = "Temporary capacity limit. Please try again in a moment."
	elif "timed out" in lower or "timeout" in lower:
		user_text = "That took too long. Try a shorter prompt or retry now."
	elif "401" in lower or "403" in lower or "auth" in lower or "key" in lower:
		user_text = "Authorization issue detected. Please verify provider credentials."
	else:
		user_text = "Could not complete that request. Please retry with a clearer prompt."
	x, y = find_empty_note_position()

	await broadcast_fn({
		"type": "add_note",
		"payload": {
			"x": x,
			"y": y,
			"text": f"{agent_name}: {user_text}",
			"color": "light-red",
			"size": "m",
			"meta": {
				"semanticRole": "error_notice",
				"source": agent_name,
				"confidence": 1.0,
				"linked_to": [],
				"addedBy": agent_name,
			},
		},
	})

	# Small yield to keep note ordering predictable relative to status updates.
	await asyncio.sleep(0.01)
