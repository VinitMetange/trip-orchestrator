"""Tests for the main Orchestrator and supervisor routing."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from src.agents.orchestrator import TripOrchestrator, AGENT_NAMES


@pytest.fixture
def orchestrator():
    """Create TripOrchestrator instance with mock agents."""
    with patch("src.agents.orchestrator.ChatBedrockConverse"), \
         patch("src.agents.orchestrator.StateGraph"), \
         patch("src.agents.orchestrator.DynamoDBSaver"):
        orch = TripOrchestrator()
        # Mock agents
        orch.planner = MagicMock()
        orch.expense = MagicMock()
        orch.tracker = MagicMock()
        orch.music = MagicMock()
        orch.insights = MagicMock()
        return orch


@pytest.mark.asyncio
async def test_supervisor_routing_to_planner(orchestrator):
    """Test supervisor routing to planner agent."""
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "next": "planner",
        "reason": "User wants an itinerary"
    })
    orchestrator.llm.invoke.return_value = mock_response
    
    state = {
        "messages": [HumanMessage(content="Plan a trip to Goa")],
        "trip_state": {}
    }
    
    result = orchestrator._supervisor_node(state)
    
    assert result["next_agent"] == "planner"


@pytest.mark.asyncio
async def test_supervisor_routing_to_expense(orchestrator):
    """Test supervisor routing to expense agent."""
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "next": "expense",
        "reason": "User shared a receipt"
    })
    orchestrator.llm.invoke.return_value = mock_response
    
    state = {
        "messages": [HumanMessage(content="[MEDIA: url] Raj paid 500")],
        "trip_state": {}
    }
    
    result = orchestrator._supervisor_node(state)
    
    assert result["next_agent"] == "expense"


@pytest.mark.asyncio
async def test_supervisor_routing_finish(orchestrator):
    """Test supervisor routing to FINISH."""
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "next": "FINISH",
        "reason": "Greeting"
    })
    orchestrator.llm.invoke.return_value = mock_response
    
    state = {
        "messages": [HumanMessage(content="Hello")],
        "trip_state": {}
    }
    
    result = orchestrator._supervisor_node(state)
    
    assert result["next_agent"] == "FINISH"


def test_route_to_agent_logic(orchestrator):
    """Test the routing function used by StateGraph."""
    state = {"next_agent": "planner"}
    assert orchestrator._route_to_agent(state) == "planner"
    
    state = {"next_agent": "FINISH"}
    assert orchestrator._route_to_agent(state) == "FINISH"
    
    state = {} # Default
    assert orchestrator._route_to_agent(state) == "FINISH"


@pytest.mark.asyncio
async def test_process_integration(orchestrator):
    """Test the full process entry point (integration-ish)."""
    # Mock graph.ainvoke to simulate execution
    orchestrator.graph.ainvoke = AsyncMock(return_value={
        "response": "Here is your plan for Goa!",
        "trip_state": {"destination": "Goa"}
    })
    
    response = await orchestrator.process(
        message="Plan for Goa",
        group_id="group_123",
        sender_phone="+919876543210",
        trip_state={},
        media_url=None
    )
    
    assert response == "Here is your plan for Goa!"
    orchestrator.graph.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_process_with_media(orchestrator):
    """Test process entry point with media URL."""
    orchestrator.graph.ainvoke = AsyncMock(return_value={"response": "Parsed receipt!"})
    
    await orchestrator.process(
        message="Receipt",
        group_id="group_123",
        sender_phone="+919876543210",
        trip_state={},
        media_url="https://example.com/receipt.jpg"
    )
    
    # Check that initial state was enriched with media info
    call_args = orchestrator.graph.ainvoke.call_args[0][0]
    last_message = call_args["messages"][-1].content
    assert "[MEDIA: https://example.com/receipt.jpg]" in last_message


@pytest.mark.asyncio
async def test_orchestrator_error_handling(orchestrator):
    """Test error handling in orchestrator process."""
    orchestrator.graph.ainvoke.side_effect = Exception("Graph error")
    
    response = await orchestrator.process(
        message="Trigger error",
        group_id="group_123",
        sender_phone="+919876543210",
        trip_state={}
    )
    
    assert "issue" in response.lower()
    assert "SOS" in response


def test_agent_names_completeness():
    """Verify all expected agent names are present."""
    assert "planner" in AGENT_NAMES
    assert "expense" in AGENT_NAMES
    assert "tracker" in AGENT_NAMES
    assert "music" in AGENT_NAMES
    assert "insights" in AGENT_NAMES
    assert "FINISH" in AGENT_NAMES


@pytest.mark.asyncio
async def test_supervisor_invalid_agent_recovery(orchestrator):
    """Test supervisor recovers from invalid agent name."""
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "next": "invalid_agent",
        "reason": "hallucination"
    })
    orchestrator.llm.invoke.return_value = mock_response
    
    state = {"messages": [HumanMessage(content="test")], "trip_state": {}}
    result = orchestrator._supervisor_node(state)
    
    # Should default to FINISH if agent is invalid
    assert result["next_agent"] == "FINISH"


@pytest.mark.asyncio
async def test_supervisor_json_parsing_resilience(orchestrator):
    """Test supervisor resilience to LLM formatting (markdown fences)."""
    mock_response = MagicMock()
    mock_response.content = "```json
{\"next\": \"planner\", \"reason\": \"test\"}
```"
    orchestrator.llm.invoke.return_value = mock_response
    
    state = {"messages": [HumanMessage(content="test")], "trip_state": {}}
    result = orchestrator._supervisor_node(state)
    
    assert result["next_agent"] == "planner"
