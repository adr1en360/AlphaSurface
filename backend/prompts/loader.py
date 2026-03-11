import os

PROMPTS_DIR = os.path.dirname(__file__)

def load_prompt(filename: str) -> str:
    path = os.path.join(PROMPTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def _persona_section(persona: dict) -> str:
    """Build a system prompt section from stored persona data."""
    if not persona:
        return ""
    lines = ["═══════════════════════════════════════════════════════",
             "USER PROFILE  (from memory — adapt your behaviour accordingly)",
             "═══════════════════════════════════════════════════════"]
    for k, v in persona.items():
        if k.startswith("_"):
            continue
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)

def build_system_prompt(mode: str, web_search: bool = False, persona: dict | None = None) -> str:
    base_prompt = load_prompt("base.txt")
    
    if mode == "think":
        suffix = load_prompt("think_mode.txt")
    else:
        suffix = load_prompt("present_mode.txt")
        
    prompt = base_prompt + "\n\n" + suffix

    if persona:
        prompt += "\n\n" + _persona_section(persona)

    if web_search:
        prompt += """

═══════════════════════════════════════════════════════
WEB SEARCH (via ResearchAgent)
═══════════════════════════════════════════════════════
When the user asks about a real-world fact, recent event, or wants information
placed on canvas — call dispatch_research("your query") immediately.
ResearchAgent will search the web and place a clean result cluster on canvas.
Do NOT try to answer from memory for factual/current queries.
Do NOT use any other search tool — only dispatch_research.
"""

    prompt += """

═══════════════════════════════════════════════════════
IMAGE GENERATION (via ImageGenAgent)
═══════════════════════════════════════════════════════
When the user asks you to generate, create, or draw an image — call
dispatch_image_gen("detailed description of the image") immediately.
ImageGenAgent will generate the image and place it on canvas.
Do NOT try to describe images in text — generate them.
"""
    return prompt
