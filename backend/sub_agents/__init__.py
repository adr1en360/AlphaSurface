import asyncio


async def emit_failure_note(broadcast_fn, agent_name: str, error: Exception | str) -> None:
	"""Broadcast a visible canvas note when a sub-agent fails."""
	message = str(error).strip() if error is not None else "unknown error"
	if len(message) > 140:
		message = message[:137] + "..."

	await broadcast_fn({
		"type": "add_note",
		"payload": {
			"x": 40,
			"y": 40,
			"text": f"{agent_name} failed: {message}",
			"color": "light-red",
			"size": "m",
		},
	})

	# Small yield to keep note ordering predictable relative to status updates.
	await asyncio.sleep(0.01)
