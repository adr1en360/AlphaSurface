"""
AlphaSurface — ADK Live agent setup.
"""

from google.adk.agents import LlmAgent
import tools as canvas_tools
from prompts.loader import build_system_prompt

def create_agent(mode: str = "think", web_search: bool = False, persona: dict | None = None) -> LlmAgent:
    tools = list(canvas_tools.ALL_TOOLS)
    return LlmAgent(
        name="AlphaSurface",
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        description="Real-time voice+vision whiteboard co-thinker",
        instruction=build_system_prompt(mode, web_search, persona),
        tools=tools,
    )
