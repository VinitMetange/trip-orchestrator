"""
TripOrchestrator - Planner Agent
Handles itinerary generation, route optimization, and booking recommendations
"""
import json
import os
from typing import Any, Dict
from langchain_core.messages import HumanMessage, AIMessage
from src.integrations.maps import GoogleMapsClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

PLANNER_SYSTEM_PROMPT = """
You are PlannerAgent for TripOrchestrator. Your job is to create detailed, optimized trip itineraries.

Capabilities:
1. Generate day-wise itineraries with timing, activities, restaurants, stays
2. Calculate budget breakdowns (accommodation, food, transport, activities)
3. Suggest optimal routes considering traffic, weather, distance
4. Recommend hotels/cabs with affiliate booking options
5. Handle multi-day trip planning

Constraints:
- Stay within budget ±10%
- Optimize for travel time and cost
- Include 30-min buffers between activities
- Prefer verified/rated places (4.0+ rating)
- Flag monsoon routes, festival crowds, toll costs

Response Format (max 100 words unless itinerary table):
- Action confirmation
- Day-wise table: Day | Time | Activity | Cost | Notes
- Budget summary
- Next action button: Approve | Edit | Modify Budget

India-specific context:
- Use Indian number format (1,50,000 not 150,000)
- Include IRCTC train options for long distances
- Flag UPI payment spots vs card-only
- Note pet-friendly, wheelchair accessibility if asked
"""

class PlannerAgent:
    def __init__(self, llm):
        self.llm = llm
        self.maps = GoogleMapsClient()

    async def run(self, state: dict) -> dict:
        """Execute planning logic"""
        messages = state["messages"]
        trip_state = state.get("trip_state", {})
        
        last_message = messages[-1].content if messages else ""
        logger.info(f"PlannerAgent processing: {last_message[:100]}")

        try:
            # Extract trip details from message
            trip_details = await self._extract_trip_details(last_message, trip_state)
            
            # Get route/maps data if destination known
            route_data = {}
            if trip_details.get("destination"):
                route_data = await self.maps.get_route_info(
                    origin=trip_details.get("origin", "Bengaluru"),
                    destination=trip_details["destination"]
                )

            # Generate itinerary
            response = await self._generate_itinerary(trip_details, route_data)
            
            return {
                **state,
                "response": response,
                "trip_state": {
                    **trip_state,
                    "phase": "planning",
                    "destination": trip_details.get("destination", trip_state.get("destination")),
                    "budget": trip_details.get("budget", trip_state.get("budget")),
                    "dates": trip_details.get("dates", trip_state.get("dates")),
                    "participants": trip_details.get("participants", trip_state.get("participants", []))
                }
            }
        except Exception as e:
            logger.error(f"PlannerAgent error: {e}", exc_info=True)
            return {
                **state,
                "response": "Hmm, planning issue. Did you mean: A) Change destination? B) Adjust budget? Reply A or B 🤔"
            }

    async def _extract_trip_details(self, message: str, existing_state: dict) -> dict:
        """Extract structured trip info from natural language"""
        extraction_prompt = f"""
Extract trip details from: '{message}'
Existing state: {json.dumps(existing_state)}

Return JSON:
{{
  "destination": "city/place",
  "origin": "starting city",
  "duration_days": int,
  "budget_per_person": int,
  "participants": int,
  "dates": "YYYY-MM-DD to YYYY-MM-DD",
  "trip_type": "road_trip|pilgrimage|beach|adventure|heritage",
  "constraints": ["veg_only", "kid_friendly", "budget_strict"]
}}
Return only JSON, no explanation.
"""
        response = self.llm.invoke([{"role": "user", "content": extraction_prompt}])
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            return json.loads(content.strip())
        except:
            return {"destination": None, "budget_per_person": existing_state.get("budget", 15000)}

    async def _generate_itinerary(self, trip_details: dict, route_data: dict) -> str:
        """Generate full itinerary using LLM"""
        context = f"""
Trip details: {json.dumps(trip_details, indent=2)}
Route data: {json.dumps(route_data, indent=2)}
"""
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Generate itinerary for: {context}"}
        ]
        response = self.llm.invoke(messages)
        return response.content

    async def approve_itinerary(self, group_id: str, itinerary: dict) -> str:
        """Confirm and save approved itinerary"""
        return f"✅ Itinerary approved! Saving to trip plan...\nTotal budget: ₹{itinerary.get('total_cost', 0):,}\nLet's go! 🚗🐈"
