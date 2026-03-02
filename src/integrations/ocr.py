"""OCR integration using Google Gemini Vision for receipt parsing.
Extracts structured expense data from receipt images.
"""
from __future__ import annotations

import base64
import re
from typing import Any, Dict, List, Optional

import google.generativeai as genai
import httpx

from src.utils.logger import get_logger
from src.utils.config import settings

logger = get_logger(__name__)

# Gemini OCR prompt for receipt parsing
RECEIPT_PARSE_PROMPT = """
You are an expert receipt parser. Extract all expense details from this receipt image.

Return a valid JSON object with this exact structure:
{
  "merchant_name": "string",
  "date": "YYYY-MM-DD or empty string",
  "total_amount": float,
  "currency": "INR",
  "items": [
    {"name": "string", "quantity": float, "unit_price": float, "total": float}
  ],
  "subtotal": float,
  "tax": float,
  "tip": float,
  "category": "Food/Transport/Accommodation/Entertainment/Shopping/Other",
  "payment_method": "string or empty"
}

Be precise with amounts. If any field is unclear, use 0 for numbers or empty string for text.
Return ONLY the JSON object, no explanation.
"""


class OCRClient:
    """Gemini Vision-powered OCR for receipt parsing."""

    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    async def parse_receipt_from_url(
        self, image_url: str, trip_id: str = "", user_id: str = ""
    ) -> Dict[str, Any]:
        """Download image from URL and parse receipt."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                image_bytes = resp.content
                content_type = resp.headers.get("content-type", "image/jpeg")
            return await self.parse_receipt_from_bytes(
                image_bytes, content_type, trip_id, user_id
            )
        except Exception as e:
            logger.error(f"OCR URL error: {e}")
            return self._error_response(str(e))

    async def parse_receipt_from_bytes(
        self,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
        trip_id: str = "",
        user_id: str = "",
    ) -> Dict[str, Any]:
        """Parse receipt from raw image bytes using Gemini Vision."""
        try:
            import json

            image_data = base64.b64encode(image_bytes).decode("utf-8")

            response = self.model.generate_content([
                RECEIPT_PARSE_PROMPT,
                {
                    "mime_type": content_type,
                    "data": image_data,
                },
            ])

            text = response.text.strip()
            # Strip markdown code fences if present
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)

            parsed = json.loads(text)
            parsed["trip_id"] = trip_id
            parsed["uploaded_by"] = user_id
            parsed["parse_success"] = True

            logger.info(
                f"Receipt parsed: {parsed.get('merchant_name')} "
                f"amount={parsed.get('total_amount')}"
            )
            return parsed

        except Exception as e:
            logger.error(f"OCR parse error: {e}")
            return self._error_response(str(e))

    async def parse_receipt_from_whatsapp_media(
        self, media_id: str, whatsapp_client: Any, trip_id: str = "", user_id: str = ""
    ) -> Dict[str, Any]:
        """Fetch media from WhatsApp and parse as receipt."""
        try:
            media_info = await whatsapp_client.get_media_url(media_id)
            media_url = media_info.get("url", "")
            if not media_url:
                return self._error_response("Could not retrieve media URL")

            async with httpx.AsyncClient(
                timeout=30,
                headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            ) as client:
                resp = await client.get(media_url)
                resp.raise_for_status()
                image_bytes = resp.content
                content_type = resp.headers.get("content-type", "image/jpeg")

            return await self.parse_receipt_from_bytes(
                image_bytes, content_type, trip_id, user_id
            )
        except Exception as e:
            logger.error(f"WhatsApp media OCR error: {e}")
            return self._error_response(str(e))

    def suggest_category(self, merchant_name: str, items: List[Dict]) -> str:
        """Rule-based category suggestion from merchant and items."""
        name_lower = merchant_name.lower()
        food_keywords = ["restaurant", "cafe", "dhaba", "hotel", "food", "pizza",
                         "burger", "swiggy", "zomato", "kitchen"]
        transport_keywords = ["petrol", "fuel", "uber", "ola", "taxi", "fuel",
                              "toll", "parking", "railway", "bus", "flight"]
        accom_keywords = ["hotel", "resort", "lodge", "inn", "hostel", "airbnb",
                          "oyo", "booking"]
        entertainment_keywords = ["cinema", "movie", "game", "park", "ticket",
                                  "event", "show", "museum"]

        for kw in food_keywords:
            if kw in name_lower:
                return "Food"
        for kw in transport_keywords:
            if kw in name_lower:
                return "Transport"
        for kw in accom_keywords:
            if kw in name_lower:
                return "Accommodation"
        for kw in entertainment_keywords:
            if kw in name_lower:
                return "Entertainment"
        return "Other"

    def calculate_equal_split(
        self, total: float, num_people: int, paid_by_user_id: str,
        participants: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Calculate equal expense splits among participants."""
        if num_people == 0:
            return []
        per_person = round(total / num_people, 2)
        # Adjust for rounding
        adjustment = round(total - per_person * num_people, 2)

        splits = []
        for i, participant in enumerate(participants):
            share = per_person + (adjustment if i == 0 else 0)
            owes_to_payer = participant["user_id"] != paid_by_user_id
            splits.append({
                "user_id": participant["user_id"],
                "name": participant["name"],
                "phone": participant.get("phone", ""),
                "share": share,
                "owes": owes_to_payer,
            })
        return splits

    def calculate_custom_split(
        self,
        total: float,
        splits_input: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Process custom split percentages or amounts."""
        results = []
        for s in splits_input:
            if "percentage" in s:
                share = round(total * s["percentage"] / 100, 2)
            else:
                share = s.get("amount", 0.0)
            results.append({
                "user_id": s["user_id"],
                "name": s["name"],
                "phone": s.get("phone", ""),
                "share": share,
            })
        return results

    @staticmethod
    def _error_response(error: str) -> Dict[str, Any]:
        return {
            "parse_success": False,
            "error": error,
            "merchant_name": "",
            "total_amount": 0.0,
            "items": [],
            "category": "Other",
        }
