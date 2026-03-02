"""pytest fixtures and test configuration."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment variables before any imports
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("DYNAMODB_TABLE_NAME", "test-trips")
os.environ.setdefault("WHATSAPP_TOKEN", "test_token")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "123456789")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "test_verify")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "test_spotify")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "test_secret")
os.environ.setdefault("GOOGLE_MAPS_API_KEY", "test_maps_key")
os.environ.setdefault("RAZORPAY_KEY_ID", "test_razorpay")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "test_secret")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini")
os.environ.setdefault("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")


@pytest.fixture
def mock_dynamodb():
    """Mock DynamoDB client."""
    with patch("boto3.resource") as mock_resource:
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        yield mock_table


@pytest.fixture
def mock_bedrock():
    """Mock AWS Bedrock client."""
    with patch("boto3.client") as mock_client:
        mock_bedrock = MagicMock()
        mock_client.return_value = mock_bedrock
        yield mock_bedrock


@pytest.fixture
def sample_trip_data():
    """Sample trip data for tests."""
    return {
        "trip_id": "trip_test_001",
        "trip_name": "Goa Trip 2025",
        "status": "planning",
        "organizer_id": "user_001",
        "members": [
            {
                "user_id": "user_001",
                "name": "Raj Kumar",
                "phone": "+919876543210",
                "role": "organizer",
                "is_active": True,
            },
            {
                "user_id": "user_002",
                "name": "Priya Singh",
                "phone": "+919876543211",
                "role": "member",
                "is_active": True,
            },
        ],
        "destination": "Goa",
        "budget_per_person": 10000.0,
        "expenses": [],
        "total_spent": 0.0,
    }


@pytest.fixture
def sample_whatsapp_message():
    """Sample WhatsApp webhook payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+919876543210",
                                "phone_number_id": "123456789",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test User"},
                                    "wa_id": "919876543210",
                                }
                            ],
                            "messages": [
                                {
                                    "id": "wamid_test_001",
                                    "from": "919876543210",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": "Plan a trip to Goa"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
