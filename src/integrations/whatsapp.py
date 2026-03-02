"""
TripOrchestrator - WhatsApp Business API Integration
Handles all WhatsApp message sending and receiving
"""
import os
import json
import httpx
from typing import Dict, List, Optional, Union
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

WHATSAPP_API_BASE = "https://graph.facebook.com/v18.0"

class WhatsAppClient:
    """
    WhatsApp Business API client for sending messages.
    Supports text, interactive buttons, media, and location messages.
    """
    
    def __init__(self):
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.api_key = os.getenv("WHATSAPP_BUSINESS_API_KEY")
        self.base_url = f"{WHATSAPP_API_BASE}/{self.phone_number_id}/messages"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def send_message(
        self,
        to: str,
        message: str,
        buttons: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Send a WhatsApp message to a phone number or group.
        
        Args:
            to: Phone number with country code (e.g., +919876543210)
            message: Text message to send (supports WhatsApp markdown)
            buttons: Optional list of interactive buttons
        
        Returns:
            dict: API response
        """
        if buttons:
            return await self._send_interactive_message(to, message, buttons)
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message[:4096]  # WhatsApp limit
            }
        }

        return await self._make_request(payload)

    async def send_to_group(
        self,
        group_members: List[str],
        message: str,
        buttons: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Send message to all members in a trip group.
        WhatsApp doesn't have bot API for groups - sends to each member.
        """
        responses = []
        async with httpx.AsyncClient(timeout=30) as client:
            for member_phone in group_members:
                try:
                    response = await self.send_message(member_phone, message, buttons)
                    responses.append({"phone": member_phone, "status": "sent", "response": response})
                except Exception as e:
                    logger.error(f"Failed to send to {member_phone}: {e}")
                    responses.append({"phone": member_phone, "status": "failed", "error": str(e)})
        return responses

    async def send_location(
        self,
        to: str,
        latitude: float,
        longitude: float,
        name: str = "",
        address: str = ""
    ) -> Dict:
        """Send a location pin"""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "location",
            "location": {
                "longitude": longitude,
                "latitude": latitude,
                "name": name,
                "address": address
            }
        }
        return await self._make_request(payload)

    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List] = None
    ) -> Dict:
        """Send a pre-approved template message (for marketing/notifications)"""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components or []
            }
        }
        return await self._make_request(payload)

    async def _send_interactive_message(
        self,
        to: str,
        message: str,
        buttons: List[Dict]
    ) -> Dict:
        """Send message with interactive quick reply buttons"""
        # Format buttons for WhatsApp API
        wa_buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": str(i),
                    "title": btn.get("text", f"Option {i+1}")[:20]  # 20 char limit
                }
            }
            for i, btn in enumerate(buttons[:3])  # Max 3 buttons
        ]
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": message[:1024]},
                "action": {"buttons": wa_buttons}
            }
        }
        return await self._make_request(payload)

    async def _make_request(self, payload: Dict) -> Dict:
        """Make HTTP request to WhatsApp API with retry logic"""
        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(3):  # Retry up to 3 times
                try:
                    response = await client.post(
                        self.base_url,
                        json=payload,
                        headers=self.headers
                    )
                    response.raise_for_status()
                    result = response.json()
                    logger.info(f"WhatsApp message sent: {result.get('messages', [{}])[0].get('id')}")
                    return result
                except httpx.HTTPStatusError as e:
                    logger.error(f"WhatsApp API error (attempt {attempt+1}): {e.response.text}")
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                except Exception as e:
                    logger.error(f"Request failed (attempt {attempt+1}): {e}")
                    if attempt == 2:
                        raise

    def parse_incoming_message(self, webhook_body: Dict) -> Optional[Dict]:
        """
        Parse incoming WhatsApp webhook message.
        Returns structured message dict or None if not a message event.
        """
        try:
            entry = webhook_body.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            
            if "messages" not in value:
                return None
            
            message = value["messages"][0]
            contact = value.get("contacts", [{}])[0]
            
            parsed = {
                "message_id": message.get("id"),
                "from": message.get("from"),
                "sender_name": contact.get("profile", {}).get("name", "Unknown"),
                "timestamp": message.get("timestamp"),
                "type": message.get("type"),
                "text": None,
                "media_url": None,
                "location": None,
                "interactive_reply": None
            }
            
            msg_type = message.get("type")
            if msg_type == "text":
                parsed["text"] = message.get("text", {}).get("body", "")
            elif msg_type in ["image", "document", "audio", "video"]:
                media_data = message.get(msg_type, {})
                parsed["media_id"] = media_data.get("id")
                parsed["media_mime"] = media_data.get("mime_type")
                # Caption as text
                parsed["text"] = media_data.get("caption", "")
            elif msg_type == "location":
                loc = message.get("location", {})
                parsed["location"] = {
                    "lat": loc.get("latitude"),
                    "lng": loc.get("longitude"),
                    "name": loc.get("name", "")
                }
                parsed["text"] = f"Location: {loc.get('latitude')},{loc.get('longitude')}"
            elif msg_type == "interactive":
                interactive = message.get("interactive", {})
                parsed["interactive_reply"] = interactive.get("button_reply", {}).get("title")
                parsed["text"] = parsed["interactive_reply"]
            
            return parsed
        except Exception as e:
            logger.error(f"Error parsing webhook message: {e}")
            return None

    async def get_media_url(self, media_id: str) -> Optional[str]:
        """Get download URL for a media file"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{WHATSAPP_API_BASE}/{media_id}",
                    headers=self.headers
                )
                response.raise_for_status()
                return response.json().get("url")
        except Exception as e:
            logger.error(f"Failed to get media URL for {media_id}: {e}")
            return None
