import os


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


# Single place to change model defaults for local development.
# If an env var is set to a non-empty value, it overrides the default here.
# If an env var is blank or missing, the default in this file is used.

# Main live voice+vision agent.
LIVE_MODEL = _env("ALPHASURFACE_MODEL_LIVE", "gemini-2.5-flash-native-audio-preview-12-2025")

# General-purpose fast model for research, youtube query optimization,
# persona analysis, and document analysis.
FAST_MODEL = _env("ALPHASURFACE_MODEL_FAST", "gemini-2.5-flash")

# Deeper reasoning model used by SuperThink.
THINKING_MODEL = _env("ALPHASURFACE_MODEL_THINKING", "gemini-2.5-pro")

# Image generation model.
IMAGE_MODEL = _env("ALPHASURFACE_MODEL_IMAGE", "gemini-2.5-flash-image")
