"""
TripOrchestrator - Expense Agent
Handles OCR receipt parsing, expense categorization, split calculation, UPI link generation
"""
import json
import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from src.integrations.ocr import GeminiOCRClient
from src.integrations.razorpay import RazorpayClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

EXPENSE_CATEGORIES = [
    "fuel", "food", "accommodation", "tickets", "shopping",
    "transport", "emergency", "miscellaneous"
]

EXPENSE_SYSTEM_PROMPT = """
You are ExpenseAgent for TripOrchestrator. You handle all money-related tasks.

Capabilities:
1. Parse receipt photos (OCR) - extract amount, vendor, items
2. Auto-categorize expenses (fuel, food, accommodation, tickets)
3. Calculate fair splits (equal or custom per participant)
4. Generate UPI payment links via Razorpay
5. Track running balances per person
6. Generate settlement summary at trip end

Split Logic:
- Shared expenses (cab, hotel room): split equally unless specified
- Personal items: assigned to individual
- Food: split by diners, not full group
- Always confirm splits before finalizing

Response Format:
- Category | Amount | Per Person | Who Owes
- Running balances: Person A (owes/owed) Rs X
- UPI links for pending settlements
- Max 100 words + balance table

Accuracy target: 100% - double check all calculations
"""

@dataclass
class ExpenseEntry:
    amount: float
    category: str
    description: str
    paid_by: str
    split_among: List[str]
    receipt_url: Optional[str] = None
    timestamp: str = ""

class ExpenseAgent:
    def __init__(self, llm):
        self.llm = llm
        self.ocr = GeminiOCRClient()
        self.razorpay = RazorpayClient()

    async def run(self, state: dict) -> dict:
        """Process expense-related messages"""
        messages = state["messages"]
        trip_state = state.get("trip_state", {})
        last_message = messages[-1].content if messages else ""
        
        logger.info(f"ExpenseAgent processing: {last_message[:100]}")

        try:
            # Check if message contains image URL (receipt)
            media_url = self._extract_media_url(last_message)
            
            if media_url:
                # OCR receipt
                receipt_data = await self.ocr.extract_receipt(media_url)
                expense = await self._process_receipt(receipt_data, last_message, trip_state)
            else:
                # Text-based expense entry
                expense = await self._parse_text_expense(last_message, trip_state)

            if expense:
                # Calculate splits
                participants = trip_state.get("participants", [])
                splits = self._calculate_splits(expense, participants)
                
                # Update balances
                updated_balances = self._update_balances(
                    trip_state.get("balances", {}),
                    expense,
                    splits
                )
                
                # Generate response
                response = self._format_expense_response(expense, splits, updated_balances)
                
                return {
                    **state,
                    "response": response,
                    "trip_state": {
                        **trip_state,
                        "balances": updated_balances,
                        "expenses": trip_state.get("expenses", []) + [vars(expense)]
                    }
                }
            
            # Ask for clarification
            return {
                **state,
                "response": "💰 How much was spent? Format: 'Paid [amount] for [what]' or share receipt photo 📸"
            }

        except Exception as e:
            logger.error(f"ExpenseAgent error: {e}", exc_info=True)
            return {
                **state,
                "response": "Hmm, expense issue. Was this: A) Fuel B) Food C) Hotel D) Other? Reply A-D 🤔"
            }

    def _extract_media_url(self, message: str) -> Optional[str]:
        """Extract media URL from message content"""
        media_match = re.search(r'\[MEDIA: (.+?)\]', message)
        return media_match.group(1) if media_match else None

    async def _process_receipt(self, receipt_data: dict, message: str, trip_state: dict) -> Optional[ExpenseEntry]:
        """Process OCR receipt data into expense entry"""
        participants = trip_state.get("participants", ["everyone"])
        paid_by = self._extract_payer(message, participants)
        
        return ExpenseEntry(
            amount=receipt_data.get("total_amount", 0),
            category=receipt_data.get("category", "miscellaneous"),
            description=receipt_data.get("vendor", "Unknown vendor"),
            paid_by=paid_by,
            split_among=receipt_data.get("split_among", participants),
            receipt_url=receipt_data.get("url")
        )

    async def _parse_text_expense(self, message: str, trip_state: dict) -> Optional[ExpenseEntry]:
        """Parse text description into expense entry using LLM"""
        participants = trip_state.get("participants", [])
        
        prompt = f"""
Parse expense from: '{message}'
Participants: {participants}

Return JSON:
{{
  "amount": float,
  "category": "fuel|food|accommodation|tickets|transport|shopping|miscellaneous",
  "description": "brief description",
  "paid_by": "person name or phone",
  "split_among": ["list of names"]
}}
Return only JSON.
"""
        response = self.llm.invoke([{"role": "user", "content": prompt}])
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            data = json.loads(content.strip())
            return ExpenseEntry(**data)
        except Exception as e:
            logger.warning(f"Could not parse expense from text: {e}")
            return None

    def _calculate_splits(self, expense: ExpenseEntry, all_participants: list) -> Dict[str, float]:
        """Calculate who owes what"""
        split_among = expense.split_among or all_participants
        if not split_among:
            split_among = ["everyone"]
        
        per_person = round(expense.amount / len(split_among), 2)
        return {person: per_person for person in split_among}

    def _update_balances(self, current_balances: dict, expense: ExpenseEntry, splits: dict) -> dict:
        """Update running balances after expense"""
        balances = dict(current_balances)
        payer = expense.paid_by
        
        # Payer gets credit for full amount
        balances[payer] = balances.get(payer, 0) + expense.amount
        
        # Each participant owes their share
        for person, amount in splits.items():
            balances[person] = balances.get(person, 0) - amount
        
        return balances

    def _format_expense_response(self, expense: ExpenseEntry, splits: dict, balances: dict) -> str:
        """Format response for WhatsApp"""
        emoji_map = {
            "fuel": "⛽", "food": "🍴", "accommodation": "🏨",
            "tickets": "🎫", "transport": "🚕", "shopping": "🛍️", "miscellaneous": "💰"
        }
        emoji = emoji_map.get(expense.category, "💰")
        per_person = list(splits.values())[0] if splits else 0
        
        response = f"{emoji} *{expense.description}*: ₹{expense.amount:,.0f}\n"
        response += f"₹{per_person:,.0f}/person ({len(splits)} sharing)\n\n"
        response += "*Running Balances:*\n"
        
        for person, balance in balances.items():
            if balance > 0:
                response += f"  ⬆️ {person}: ₹{balance:,.0f} to receive\n"
            elif balance < 0:
                response += f"  ⬇️ {person}: ₹{abs(balance):,.0f} owes\n"
        
        return response.strip()

    def _extract_payer(self, message: str, participants: list) -> str:
        """Extract who paid from message context"""
        message_lower = message.lower()
        for participant in participants:
            if participant.lower() in message_lower:
                return participant
        return "me"  # Default to message sender

    async def generate_settlement_links(self, balances: dict) -> str:
        """Generate UPI payment links for final settlement"""
        debtors = {k: abs(v) for k, v in balances.items() if v < 0}
        creditors = {k: v for k, v in balances.items() if v > 0}
        
        settlement_links = []
        for debtor, amount in debtors.items():
            for creditor, credit in creditors.items():
                if amount > 0 and credit > 0:
                    pay_amount = min(amount, credit)
                    link = await self.razorpay.create_payment_link(
                        amount=int(pay_amount * 100),  # paise
                        description=f"TripOrchestrator settlement: {debtor} to {creditor}",
                        customer_name=debtor
                    )
                    settlement_links.append({
                        "from": debtor, "to": creditor,
                        "amount": pay_amount, "link": link
                    })
        
        if not settlement_links:
            return "🎉 All settled! No pending payments."
        
        response = "💳 *Settlement Links:*\n\n"
        for s in settlement_links:
            response += f"{s['from']} → {s['to']}: ₹{s['amount']:,.0f}\n"
            response += f"   Pay: {s['link']}\n\n"
        
        return response.strip()
