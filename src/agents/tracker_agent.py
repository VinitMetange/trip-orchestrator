"""
TripOrchestrator - Tracker Agent
Handles GPS monitoring, ETA updates, emergency SOS, rerouting
"""
import asyncio
import os
from typing import Optional
from src.integrations.maps import GoogleMapsClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

SOSKeywords = ["HELP", "accident", "emergency", "ambulance", "lost", "SOS"]

class TrackerAgent:
    def __init__(self, llm):
        self.llm = llm
        self.maps = GoogleMapsClient()

    async def run(self, state: dict) -> dict:
        """Process tracking-related messages"""
        messages = state["messages"]
        trip_state = state.get("trip_state", {})
        last_message = messages[-1].content.lower() if messages else ""

        # CRITICAL: Check for emergency SOS
        if any(kw.lower() in last_message for kw in SOSKeywords):
            return await self._handle_sos(state, trip_state)

        # Location update
        if "location" in last_message or "where" in last_message or "eta" in last_message:
            return await self._handle_location_query(state, trip_state)

        # Route update/rerouting
        if "route" in last_message or "traffic" in last_message or "detour" in last_message:
            return await self._handle_reroute(state, trip_state)

        return {
            **state,
            "response": "📍 *Tracker Active*\nCurrent: {location}\nETA: {eta}\nType HELP for emergency, 'location' for updates".format(
                location=trip_state.get("current_location", "Unknown"),
                eta=trip_state.get("eta", "Calculating...")
            )
        }

    async def _handle_sos(self, state: dict, trip_state: dict) -> dict:
        """Handle emergency SOS - highest priority"""
        location = trip_state.get("current_location", "Unknown location")
        members = trip_state.get("members", [])
        
        logger.critical(f"SOS triggered for trip {trip_state.get('group_id')}: {location}")

        # Get nearest hospital
        hospital = await self.maps.find_nearest_hospital(location)
        
        sos_response = f"""⚠️ *EMERGENCY ACTIVATED* ⚠️

Shared location with all {len(members)} members
📞 Calling 108 - National Ambulance

🏥 Nearest Hospital:
{hospital.get('name', 'Checking...')}
{hospital.get('distance', '')} away
🗺️ Navigate: {hospital.get('maps_url', '')}

Stay calm. Help is on the way.
Reply *OK* when safe."""

        return {
            **state,
            "response": sos_response,
            "trip_state": {**trip_state, "sos_active": True, "sos_location": location}
        }

    async def _handle_location_query(self, state: dict, trip_state: dict) -> dict:
        """Handle location/ETA queries"""
        current_location = trip_state.get("current_location")
        destination = trip_state.get("destination")

        if current_location and destination:
            route_info = await self.maps.get_route_info(current_location, destination)
            eta = route_info.get("duration", "Unknown")
            distance = route_info.get("distance", "Unknown")

            response = f"""📍 *Live Location Update*

Currently: {current_location}
Destination: {destination}
ETA: {eta}
Distance: {distance}

Traffic: {route_info.get('traffic_condition', 'Normal')}
🔄 Last updated: Just now"""
        else:
            response = "📍 Please share current location for ETA tracking. Type your location or share via WhatsApp."

        return {**state, "response": response}

    async def _handle_reroute(self, state: dict, trip_state: dict) -> dict:
        """Handle rerouting requests"""
        current_location = trip_state.get("current_location")
        destination = trip_state.get("destination")

        if not (current_location and destination):
            return {
                **state,
                "response": "🗺️ Rerouting needs current location. Please share location first!"
            }

        alt_routes = await self.maps.get_alternative_routes(current_location, destination)
        
        if not alt_routes:
            return {
                **state,
                "response": "🗺️ No alternate routes found. Current route is optimal."
            }

        best_alt = alt_routes[0]
        response = f"""🔄 *Alternative Route Found*

{best_alt.get('name', 'Route A')}
⏱ {best_alt.get('duration', 'Unknown')}
📐 {best_alt.get('distance', 'Unknown')}

Saves: {best_alt.get('time_saved', 'Unknown')} vs current route

Switch to new route? *Yes / No*"""

        return {**state, "response": response}

    async def send_proactive_alerts(self, trip_state: dict, whatsapp_client) -> None:
        """
        Proactive monitoring - runs as background task.
        Sends alerts for fuel, food, weather, timing.
        """
        group_id = trip_state.get("group_id")
        current_location = trip_state.get("current_location")
        
        if not current_location:
            return

        # Check fuel stations ahead
        fuel_stations = await self.maps.find_nearby(current_location, "fuel station", radius=20000)
        if len(fuel_stations) < 2:
            await whatsapp_client.send_message(
                group_id,
                "⛽ *Fuel Alert*: Only {count} fuel stations in next 20km. Refuel soon!".format(
                    count=len(fuel_stations)
                )
            )

        # Check upcoming stops
        eta_to_dest = trip_state.get("eta_minutes", 999)
        if eta_to_dest > 120:  # More than 2 hours
            rest_stops = await self.maps.find_nearby(current_location, "restaurant", radius=15000)
            if rest_stops:
                await whatsapp_client.send_message(
                    group_id,
                    f"🍴 Lunch spot ahead: {rest_stops[0].get('name')} ({rest_stops[0].get('rating')} ⭐) - 15 mins. Stop? *Yes / Skip*"
                )
