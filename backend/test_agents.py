import pytest
from pydantic import BaseModel
import asyncio
from unittest.mock import AsyncMock, patch
from sub_agents.research_agent import run_research
from sub_agents.persona_agent import PersonaAgent, USER_ID
from memory import memory_store

pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
def mock_memory():
    # Keep the default MemoryStore pointing at the testing db
    import memory
    import os
    original_store = memory._store
    db_file = "test_memory.db"
    if os.path.exists(db_file):
        os.remove(db_file)
    memory._store = memory.SQLiteMemoryStore(db_file)
    yield
    memory._store = original_store
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass

async def test_research_agent_success():
    """Test that the research agent successfully parses output and broadcasts it to canvas."""
    
    # Mocking the session return value to simulate ADK Agent finish
    mock_session = AsyncMock()
    mock_session.state = {
        "research_result": {
            "title": "Quantum Computing",
            "bullets": ["It uses qubits", "It is very fast"],
            "source_url": "https://example.com/qc",
            "source_label": "Example Science"
        }
    }

    mock_broadcast = AsyncMock()

    with patch('google.adk.sessions.InMemorySessionService.get_session', return_value=mock_session):
        # Prevent the runner loop from hanging or calling real LLM
        with patch('google.adk.runners.Runner.run_async') as mock_run:
            async def dummy_run(*args, **kwargs):
                yield AsyncMock(is_final_response=lambda: True)
            mock_run.side_effect = dummy_run

            # Run the handler
            await run_research({"query": "What is quantum computing?"}, mock_broadcast)

    # Verify canvas events were broadcast
    assert mock_broadcast.call_count > 0

    # Ensure add_geo (title) was called
    calls = mock_broadcast.call_args_list
    add_geo_calls = [c for c in calls if c[0][0].get("type") == "add_geo"]
    assert len(add_geo_calls) == 1
    assert add_geo_calls[0][0][0]["text"] == "Quantum Computing"

    # Verify 2 bullets
    add_note_calls = [c for c in calls if c[0][0].get("type") == "add_note"]
    assert len(add_note_calls) == 2


async def test_persona_agent_success():
    """Test that persona agent extracts traits and saves to memory."""
    agent = PersonaAgent()
    
    # Mock canvas text
    mock_canvas = {"total_text_shapes": 1, "sticky_notes": [{"text": "I like python"}]}
    
    mock_session = AsyncMock()
    mock_session.state = {
        "persona_updates": {
            "updates": {"communication_style": "textual"},
            "append_traits": ["likes python"]
        }
    }

    with patch('tools.scan_canvas_text', return_value=mock_canvas):
        with patch('google.adk.sessions.InMemorySessionService.get_session', return_value=mock_session):
             with patch('google.adk.runners.Runner.run_async') as mock_run:
                 async def dummy_run(*args, **kwargs):
                     yield AsyncMock()
                 mock_run.side_effect = dummy_run
                 
                 # Initialize empty memory
                 await memory_store().write(USER_ID, {})

                 # Run analysis
                 await agent._analyze()
                 
    # Verify memory was merged
    profile = await memory_store().read(USER_ID)
    assert profile.get("communication_style") == "textual"
    assert "likes python" in profile.get("observed_traits", [])
