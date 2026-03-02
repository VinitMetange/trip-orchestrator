"""
TripOrchestrator - Insights Agent
Handles post-trip analytics, savings reports, NPS surveys
"""
import json
from datetime import datetime
from typing import Dict, List, Optional
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class InsightsAgent:
    def __init__(self, llm):
        self.llm = llm

    async def run(self, state: dict) -> dict:
        """Generate insights and analytics"""
        messages = state["messages"]
        trip_state = state.get("trip_state", {})
        last_message = messages[-1].content.lower() if messages else ""

        if "report" in last_message or "summary" in last_message:
            return await self._generate_trip_report(state, trip_state)
        elif "nps" in last_message or "rate" in last_message:
            return await self._request_nps(state, trip_state)
        elif "savings" in last_message or "saved" in last_message:
            return await self._calculate_savings(state, trip_state)
        else:
            return await self._generate_trip_report(state, trip_state)

    async def _generate_trip_report(self, state: dict, trip_state: dict) -> dict:
        """Generate comprehensive post-trip report"""
        expenses = trip_state.get("expenses", [])
        balances = trip_state.get("balances", {})
        destination = trip_state.get("destination", "Trip")
        dates = trip_state.get("dates", "Recent trip")

        # Calculate totals by category
        category_totals = {}
        total_spend = 0
        for expense in expenses:
            cat = expense.get("category", "miscellaneous")
            amount = expense.get("amount", 0)
            category_totals[cat] = category_totals.get(cat, 0) + amount
            total_spend += amount

        participants_count = len(trip_state.get("participants", [1]))
        per_person = total_spend / max(participants_count, 1)

        report = f"""📊 *{destination} Trip Summary*
{dates}

*Total Spent: ₹{total_spend:,.0f}*
Per person: ₹{per_person:,.0f}

*Breakdown:*
"""
        emoji_map = {
            "fuel": "⛽", "food": "🍴", "accommodation": "🏨",
            "tickets": "🎫", "transport": "🚕", "shopping": "🛍️"
        }
        for cat, amount in sorted(category_totals.items(), key=lambda x: -x[1]):
            emoji = emoji_map.get(cat, "💰")
            pct = (amount / total_spend * 100) if total_spend > 0 else 0
            report += f"{emoji} {cat.title()}: ₹{amount:,.0f} ({pct:.0f}%)\n"

        report += "\n*Final Balances:*\n"
        for person, balance in balances.items():
            if balance > 0:
                report += f"  🟢 {person}: gets ₹{abs(balance):,.0f}\n"
            elif balance < 0:
                report += f"  🔴 {person}: owes ₹{abs(balance):,.0f}\n"

        report += "\nRate your trip 1-10? 🙏"

        return {
            **state,
            "response": report,
            "trip_state": {**trip_state, "phase": "completed"}
        }

    async def _calculate_savings(self, state: dict, trip_state: dict) -> dict:
        """Calculate how much the group saved vs average"""
        expenses = trip_state.get("expenses", [])
        destination = trip_state.get("destination", "your destination")
        total = sum(e.get("amount", 0) for e in expenses)
        
        # Estimated average (hardcoded baseline - can be data-driven)
        avg_multipliers = {
            "goa": 18000, "manali": 12000, "kerala": 15000,
            "rajasthan": 20000, "himachal": 14000
        }
        dest_lower = destination.lower()
        avg = next((v for k, v in avg_multipliers.items() if k in dest_lower), 15000)
        participants = len(trip_state.get("participants", [1]))
        per_person = total / max(participants, 1)
        savings = max(0, avg - per_person)

        response = f"""💰 *Savings Analysis*

Your trip: ₹{per_person:,.0f}/person
Average {destination} trip: ₹{avg:,.0f}/person

You saved: ₹{savings:,.0f}/person! 🎉

Top saving areas: Use TripOrchestrator for next trip to save even more!"""

        return {**state, "response": response}

    async def _request_nps(self, state: dict, trip_state: dict) -> dict:
        """Request NPS rating from group"""
        destination = trip_state.get("destination", "your trip")
        response = f"""🙏 *Rate your {destination} experience!*

Reply with a number 1-10:
1-3 = Not great
4-6 = It was okay
7-8 = Had fun!
9-10 = Amazing!

We use ratings to improve TripOrchestrator for your next adventure 🚗"""
        return {**state, "response": response}
