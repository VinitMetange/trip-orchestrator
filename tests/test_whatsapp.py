"""Tests for WhatsApp Business API integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.integrations.whatsapp import WhatsAppClient


@pytest.fixture
def whatsapp_client():
    """Create WhatsApp client instance."""
    return WhatsAppClient()


@pytest.mark.asyncio
async def test_send_text_message(whatsapp_client):
    """Test sending basic text message."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "messages": [{"id": "wamid_test_123"}]
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        
        result = await whatsapp_client.send_message(
            to="+919876543210",
            message="Test message"
        )
        
        assert result["messages"][0]["id"] == "wamid_test_123"


@pytest.mark.asyncio
async def test_send_message_with_buttons(whatsapp_client):
    """Test sending interactive message with buttons."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "messages": [{"id": "wamid_button_123"}]
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        
        buttons = [
            {"text": "Option 1"},
            {"text": "Option 2"},
            {"text": "Option 3"}
        ]
        
        result = await whatsapp_client.send_message(
            to="+919876543210",
            message="Choose an option:",
            buttons=buttons
        )
        
        assert result["messages"][0]["id"] == "wamid_button_123"


@pytest.mark.asyncio
async def test_send_to_group(whatsapp_client):
    """Test sending message to multiple group members."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "messages": [{"id": "wamid_group_123"}]
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        
        group_members = ["+919876543210", "+919876543211", "+919876543212"]
        
        results = await whatsapp_client.send_to_group(
            group_members=group_members,
            message="Group announcement"
        )
        
        assert len(results) == 3
        assert all(r["status"] == "sent" for r in results)


@pytest.mark.asyncio
async def test_send_location(whatsapp_client):
    """Test sending location pin."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "messages": [{"id": "wamid_location_123"}]
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        
        result = await whatsapp_client.send_location(
            to="+919876543210",
            latitude=15.2993,
            longitude=74.1240,
            name="Goa Beach",
            address="Calangute, Goa"
        )
        
        assert result["messages"][0]["id"] == "wamid_location_123"


@pytest.mark.asyncio
async def test_send_template(whatsapp_client):
    """Test sending pre-approved template message."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "messages": [{"id": "wamid_template_123"}]
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        
        result = await whatsapp_client.send_template(
            to="+919876543210",
            template_name="trip_reminder",
            language_code="en_US",
            components=[]
        )
        
        assert result["messages"][0]["id"] == "wamid_template_123"


def test_parse_text_message(whatsapp_client, sample_whatsapp_message):
    """Test parsing incoming text message from webhook."""
    parsed = whatsapp_client.parse_incoming_message(sample_whatsapp_message)
    
    assert parsed is not None
    assert parsed["message_id"] == "wamid_test_001"
    assert parsed["from"] == "919876543210"
    assert parsed["sender_name"] == "Test User"
    assert parsed["type"] == "text"
    assert parsed["text"] == "Plan a trip to Goa"


def test_parse_image_message(whatsapp_client):
    """Test parsing image message with caption."""
    webhook_data = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "id": "wamid_image_001",
                        "from": "919876543210",
                        "timestamp": "1700000000",
                        "type": "image",
                        "image": {
                            "id": "img_123",
                            "mime_type": "image/jpeg",
                            "caption": "Check this receipt"
                        }
                    }],
                    "contacts": [{
                        "profile": {"name": "Test User"},
                        "wa_id": "919876543210"
                    }]
                }
            }]
        }]
    }
    
    parsed = whatsapp_client.parse_incoming_message(webhook_data)
    
    assert parsed is not None
    assert parsed["type"] == "image"
    assert parsed["media_id"] == "img_123"
    assert parsed["text"] == "Check this receipt"


def test_parse_location_message(whatsapp_client):
    """Test parsing location message."""
    webhook_data = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "id": "wamid_loc_001",
                        "from": "919876543210",
                        "timestamp": "1700000000",
                        "type": "location",
                        "location": {
                            "latitude": 15.2993,
                            "longitude": 74.1240,
                            "name": "Goa Beach"
                        }
                    }],
                    "contacts": [{
                        "profile": {"name": "Test User"},
                        "wa_id": "919876543210"
                    }]
                }
            }]
        }]
    }
    
    parsed = whatsapp_client.parse_incoming_message(webhook_data)
    
    assert parsed is not None
    assert parsed["type"] == "location"
    assert parsed["location"]["lat"] == 15.2993
    assert parsed["location"]["lng"] == 74.1240


def test_parse_interactive_reply(whatsapp_client):
    """Test parsing interactive button reply."""
    webhook_data = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "id": "wamid_interactive_001",
                        "from": "919876543210",
                        "timestamp": "1700000000",
                        "type": "interactive",
                        "interactive": {
                            "button_reply": {
                                "id": "1",
                                "title": "Option 1"
                            }
                        }
                    }],
                    "contacts": [{
                        "profile": {"name": "Test User"},
                        "wa_id": "919876543210"
                    }]
                }
            }]
        }]
    }
    
    parsed = whatsapp_client.parse_incoming_message(webhook_data)
    
    assert parsed is not None
    assert parsed["type"] == "interactive"
    assert parsed["interactive_reply"] == "Option 1"
    assert parsed["text"] == "Option 1"


def test_parse_invalid_webhook(whatsapp_client):
    """Test parsing invalid webhook payload."""
    invalid_data = {"invalid": "structure"}
    
    parsed = whatsapp_client.parse_incoming_message(invalid_data)
    
    assert parsed is None


@pytest.mark.asyncio
async def test_retry_logic_on_failure(whatsapp_client):
    """Test retry mechanism on API failure."""
    with patch("httpx.AsyncClient") as mock_client:
        # First two attempts fail, third succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.raise_for_status.side_effect = Exception("API Error")
        
        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {
            "messages": [{"id": "wamid_retry_123"}]
        }
        mock_response_success.raise_for_status = MagicMock()
        
        mock_post = AsyncMock(side_effect=[
            mock_response_fail,
            mock_response_fail,
            mock_response_success
        ])
        
        mock_client.return_value.__aenter__.return_value.post = mock_post
        
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await whatsapp_client.send_message(
                to="+919876543210",
                message="Test retry"
            )
        
        assert result["messages"][0]["id"] == "wamid_retry_123"
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_get_media_url(whatsapp_client):
    """Test getting download URL for media."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "url": "https://example.com/media/download"
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        
        url = await whatsapp_client.get_media_url("media_123")
        
        assert url == "https://example.com/media/download"


@pytest.mark.asyncio
async def test_message_length_truncation(whatsapp_client):
    """Test that messages are truncated to WhatsApp limits."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "messages": [{"id": "wamid_long_123"}]
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post
        
        # Create a message longer than 4096 characters
        long_message = "x" * 5000
        
        await whatsapp_client.send_message(
            to="+919876543210",
            message=long_message
        )
        
        # Verify the call was made with truncated message
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert len(payload["text"]["body"]) <= 4096
