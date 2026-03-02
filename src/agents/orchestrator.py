"""
TripOrchestrator - Main Orchestrator Agent
LangGraph Supervisor pattern for multi-agent coordination
"""
from typing import Annotated, Sequence, TypedDict, Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_aws import ChatBedrockConverse
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.dynamodb import DynamoDBSaver
from src.agents.planner_agent import PlannerAgent
from src.agents.expense_agent import ExpenseAgent
from src.agents.tracker_agent import TrackerAgent
from src.agents.music_agent import MusicAgent
from src.agents.insights_agent import InsightsAgent
from src.models.trip_state import TripState
from src.utils.logger import setup_logger
import json, re, os

logger = setup_logger(__name__)

AGENT_NAMES = ["planner", "expense", "tracker", "music", "insights", "FINISH"]

class AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    trip_state: dict
    next_agent: str
    response: str

class TripOrchestrator:
    """
    Main orchestrator using LangGraph supervisor pattern.
    Routes intent to specialized sub-agents.
    """
    def __init__(self):
        self.llm = ChatBedrockConverse(
            model=os.getenv("AWS_BEDROCK_MODEL", "anthropic.claude-3-5-sonnet-20240620-v1:0"),
            region_name=os.getenv("AWS_REGION", "ap-south-1"),
            temperature=0,
            max_tokens=2000,
        )
        self.planner = PlannerAgent(self.llm)
        self.expense = ExpenseAgent(self.llm)
        self.tracker = TrackerAgent(self.llm)
        self.music = MusicAgent(self.llm)
        self.insights = InsightsAgent(self.llm)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph multi-agent supervisor graph"""
        workflow = StateGraph(AgentState)

        # Add supervisor node
        workflow.add_node("supervisor", self._supervisor_node)

        # Add agent nodes
        workflow.add_node("planner", self.planner.run)
        workflow.add_node("expense", self.expense.run)
        workflow.add_node("tracker", self.tracker.run)
        workflow.add_node("music", self.music.run)
        workflow.add_node("insights", self.insights.run)

        # Supervisor routes to agents
        workflow.add_conditional_edges(
            "supervisor",
            self._route_to_agent,
            {
                "planner": "planner",
                "expense": "expense",
                "tracker": "tracker",
                "music": "music",
                "insights": "insights",
                "FINISH": END,
            }
        )

        # All agents return to supervisor
        for agent in ["planner", "expense", "tracker", "music", "insights"]:
            workflow.add_edge(agent, "supervisor")

        workflow.set_entry_point("supervisor")
        return workflow.compile(
            checkpointer=DynamoDBSaver.from_conn_info(
                table_name=os.getenv("DYNAMODB_TABLE", "trip-orchestrator-state"),
                region_name=os.getenv("AWS_REGION", "ap-south-1")
            )
        )

    def _supervisor_node(self, state: AgentState) -> AgentState:
        """Supervisor decides which agent to route to"""
        system_prompt = """
You are TripOrchestrator supervisor. Analyze user messages and route to the right agent.

Agents:
- planner: trip planning, itinerary, hotels, routes, weather
- expense: payments, receipts, splits, UPI, balances
- tracker: GPS, location, ETA, emergency SOS
- music: Spotify, playlists, songs, music control
- insights: post-trip reports, analytics, summaries
- FINISH: simple greetings, confirmations needing no agent

Trip context: {trip_state}

Respond with JSON: {{"next": "agent_name", "reason": "brief reason"}}
""".format(trip_state=json.dumps(state.get("trip_state", {}), indent=2)[:500])

        messages = state["messages"]
        response = self.llm.invoke([
            {"role": "system", "content": system_prompt},
            *[{"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
              for m in messages[-5:]]  # Last 5 messages for context
        ])

        try:
            # Parse JSON from response
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            routing = json.loads(content.strip())
            next_agent = routing.get("next", "FINISH")
            if next_agent not in AGENT_NAMES:
                next_agent = "FINISH"
        except Exception as e:
            logger.error(f"Supervisor routing error: {e}")
            next_agent = "FINISH"

        logger.info(f"Supervisor routing to: {next_agent}")
        return {**state, "next_agent": next_agent}

    def _route_to_agent(self, state: AgentState) -> str:
        """Extract the next agent from state"""
        return state.get("next_agent", "FINISH")

    async def process(
        self,
        message: str,
        group_id: str,
        sender_phone: str,
        trip_state: dict,
        media_url: str = None
    ) -> str:
        """
        Main entry point - process user message and return response.
        
        Args:
            message: User message text
            group_id: WhatsApp group ID
            sender_phone: Sender phone number
            trip_state: Current trip state from DynamoDB
            media_url: Optional image/audio URL
        
        Returns:
            str: Agent response to send back to WhatsApp
        """
        config = {"configurable": {"thread_id": group_id}}
        
        # Enrich message with context
        enriched_message = f"[{sender_phone}]: {message}"
        if media_url:
            enriched_message += f"\n[MEDIA: {media_url}]"

        initial_state = AgentState(
            messages=[HumanMessage(content=enriched_message)],
            trip_state=trip_state,
            next_agent="",
            response=""
        )

        try:
            final_state = await self.graph.ainvoke(initial_state, config)
            response = final_state.get("response", "I'm here! How can I help with your trip? 🚗")
            return response
        except Exception as e:
            logger.error(f"Orchestrator error for group {group_id}: {e}", exc_info=True)
            return "Hmm, ran into an issue. Try again? If urgent, type HELP for emergency support. 🆘"
