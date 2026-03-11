import pytest

def test_tool_imports():
    from tools import ALL_TOOLS, canvas_action_queue, canvas_state
    
    # Verify that the tools list is actually assembled
    assert len(ALL_TOOLS) > 0, "ALL_TOOLS should be populated"
    
    # Verify State isn't broken
    assert isinstance(canvas_state, dict), "canvas_state should be a dictionary"
    assert "shapes" in canvas_state, "canvas_state must contain shapes key"

def test_agent_initialization():
    from agent import create_agent
    from prompts.loader import load_prompt
    
    # Try to load base prompt
    base_prompt = load_prompt("base.txt")
    assert base_prompt is not None and len(base_prompt) > 0, "Base prompt failed to load"
    
    # Make sure agent builds correctly
    agent = create_agent(mode="think", web_search=False)
    assert agent.name == "AlphaSurface"
    assert len(agent.tools) > 0
    
def test_live_session_import():
    from live_session import AlphaSurfaceAgent
    
    # Make sure it can be instantiated without errors
    async def dummy_broadcast(payload: dict):
        pass
        
    s = AlphaSurfaceAgent(dummy_broadcast)
    assert s.mode == "think", "Default mode should be think"
