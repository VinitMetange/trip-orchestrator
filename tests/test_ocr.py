"""Tests for OCR integration and expense split logic."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.ocr import OCRClient


SAMPLE_RECEIPT_JSON = {
    "merchant_name": "Taj Restaurant",
    "date": "2025-01-15",
    "total_amount": 1800.0,
    "currency": "INR",
    "items": [
        {"name": "Butter Chicken", "quantity": 2, "unit_price": 450.0, "total": 900.0},
        {"name": "Naan", "quantity": 6, "unit_price": 50.0, "total": 300.0},
        {"name": "Lassi", "quantity": 3, "unit_price": 100.0, "total": 300.0},
        {"name": "Gulab Jamun", "quantity": 3, "unit_price": 100.0, "total": 300.0},
    ],
    "subtotal": 1800.0,
    "tax": 0.0,
    "tip": 0.0,
    "category": "Food",
    "payment_method": "UPI",
}


class TestOCRClient:
    @pytest.fixture
    def ocr_client(self):
        with patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel") as mock_model:
            client = OCRClient()
            client.model = mock_model.return_value
            yield client

    def test_suggest_category_food(self, ocr_client):
        category = ocr_client.suggest_category("Taj Restaurant", [])
        assert category == "Food"

    def test_suggest_category_transport(self, ocr_client):
        category = ocr_client.suggest_category("Uber Technologies", [])
        assert category == "Transport"

    def test_suggest_category_accommodation(self, ocr_client):
        category = ocr_client.suggest_category("OYO Hotel Goa", [])
        assert category == "Accommodation"

    def test_suggest_category_other(self, ocr_client):
        category = ocr_client.suggest_category("Random Store", [])
        assert category == "Other"

    def test_calculate_equal_split_3_people(self, ocr_client):
        participants = [
            {"user_id": "u1", "name": "Alice", "phone": "+91999"},
            {"user_id": "u2", "name": "Bob", "phone": "+91998"},
            {"user_id": "u3", "name": "Carol", "phone": "+91997"},
        ]
        splits = ocr_client.calculate_equal_split(
            total=1800.0,
            num_people=3,
            paid_by_user_id="u1",
            participants=participants,
        )
        assert len(splits) == 3
        # Total should sum to 1800
        total = sum(s["share"] for s in splits)
        assert abs(total - 1800.0) < 0.01
        # Payer should have owes=False
        payer = next(s for s in splits if s["user_id"] == "u1")
        assert payer["owes"] is False

    def test_calculate_equal_split_single_person(self, ocr_client):
        participants = [{"user_id": "u1", "name": "Solo", "phone": "+91999"}]
        splits = ocr_client.calculate_equal_split(
            total=500.0,
            num_people=1,
            paid_by_user_id="u1",
            participants=participants,
        )
        assert len(splits) == 1
        assert splits[0]["share"] == 500.0

    def test_calculate_equal_split_zero_people(self, ocr_client):
        splits = ocr_client.calculate_equal_split(
            total=500.0,
            num_people=0,
            paid_by_user_id="u1",
            participants=[],
        )
        assert splits == []

    def test_calculate_custom_split_percentage(self, ocr_client):
        splits_input = [
            {"user_id": "u1", "name": "Alice", "phone": "+91999", "percentage": 50},
            {"user_id": "u2", "name": "Bob", "phone": "+91998", "percentage": 30},
            {"user_id": "u3", "name": "Carol", "phone": "+91997", "percentage": 20},
        ]
        splits = ocr_client.calculate_custom_split(
            total=1000.0,
            splits_input=splits_input,
        )
        alice = next(s for s in splits if s["user_id"] == "u1")
        bob = next(s for s in splits if s["user_id"] == "u2")
        carol = next(s for s in splits if s["user_id"] == "u3")
        assert alice["share"] == 500.0
        assert bob["share"] == 300.0
        assert carol["share"] == 200.0

    @pytest.mark.asyncio
    async def test_parse_receipt_from_bytes_success(self, ocr_client):
        mock_response = MagicMock()
        mock_response.text = json.dumps(SAMPLE_RECEIPT_JSON)
        ocr_client.model.generate_content = MagicMock(return_value=mock_response)

        result = await ocr_client.parse_receipt_from_bytes(
            image_bytes=b"fake_image_data",
            content_type="image/jpeg",
            trip_id="trip_001",
            user_id="user_001",
        )
        assert result["parse_success"] is True
        assert result["merchant_name"] == "Taj Restaurant"
        assert result["total_amount"] == 1800.0
        assert result["trip_id"] == "trip_001"

    @pytest.mark.asyncio
    async def test_parse_receipt_error_handling(self, ocr_client):
        ocr_client.model.generate_content = MagicMock(
            side_effect=Exception("API error")
        )
        result = await ocr_client.parse_receipt_from_bytes(
            image_bytes=b"fake_data",
        )
        assert result["parse_success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_parse_receipt_with_markdown_fence(self, ocr_client):
        mock_response = MagicMock()
        mock_response.text = f"```json\n{json.dumps(SAMPLE_RECEIPT_JSON)}\n```"
        ocr_client.model.generate_content = MagicMock(return_value=mock_response)

        result = await ocr_client.parse_receipt_from_bytes(
            image_bytes=b"fake_image_data",
        )
        assert result["parse_success"] is True
        assert result["merchant_name"] == "Taj Restaurant"
