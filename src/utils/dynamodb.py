"""DynamoDB data access layer for TripOrchestrator.
Handles all CRUD operations for trip state with optimistic locking.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from src.utils.logger import get_logger
from src.utils.config import settings

logger = get_logger(__name__)


def _serialize(obj: Any) -> Any:
    """Convert Python objects to DynamoDB-compatible types."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _deserialize(obj: Any) -> Any:
    """Convert DynamoDB types back to Python types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _deserialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deserialize(v) for v in obj]
    return obj


class DynamoDBClient:
    """Thread-safe DynamoDB client for trip state management."""

    def __init__(self):
        self._dynamodb = boto3.resource(
            "dynamodb",
            region_name=settings.AWS_REGION,
        )
        self._table = self._dynamodb.Table(settings.DYNAMODB_TABLE_NAME)

    async def get_trip(self, trip_id: str) -> Optional[Dict[str, Any]]:
        """Fetch trip state by trip_id."""
        try:
            response = self._table.get_item(
                Key={"trip_id": trip_id},
                ConsistentRead=True,
            )
            item = response.get("Item")
            return _deserialize(item) if item else None
        except ClientError as e:
            logger.error(f"DynamoDB get_trip error: {e.response['Error']['Message']}")
            raise

    async def save_trip(self, trip_data: Dict[str, Any]) -> None:
        """Save (upsert) a full trip state."""
        try:
            item = _serialize(trip_data)
            item["updated_at"] = datetime.utcnow().isoformat()
            self._table.put_item(Item=item)
            logger.info(f"Trip saved: {trip_data.get('trip_id')}")
        except ClientError as e:
            logger.error(f"DynamoDB save_trip error: {e.response['Error']['Message']}")
            raise

    async def update_trip_fields(
        self, trip_id: str, updates: Dict[str, Any]
    ) -> None:
        """Partially update specific fields of a trip."""
        try:
            update_expr_parts = []
            expr_attr_names: Dict[str, str] = {}
            expr_attr_values: Dict[str, Any] = {}

            for i, (key, value) in enumerate(updates.items()):
                placeholder = f"#attr{i}"
                value_placeholder = f":val{i}"
                update_expr_parts.append(f"{placeholder} = {value_placeholder}")
                expr_attr_names[placeholder] = key
                expr_attr_values[value_placeholder] = _serialize(value)

            # Always update the updated_at timestamp
            update_expr_parts.append("#updated_at = :updated_at")
            expr_attr_names["#updated_at"] = "updated_at"
            expr_attr_values[":updated_at"] = datetime.utcnow().isoformat()

            self._table.update_item(
                Key={"trip_id": trip_id},
                UpdateExpression="SET " + ", ".join(update_expr_parts),
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
            )
        except ClientError as e:
            logger.error(
                f"DynamoDB update_trip_fields error: {e.response['Error']['Message']}"
            )
            raise

    async def get_trips_by_member(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Query trips where user is a member (GSI: member_index)."""
        try:
            response = self._table.query(
                IndexName="member_index",
                KeyConditionExpression=Key("organizer_id").eq(user_id),
                Limit=limit,
                ScanIndexForward=False,
            )
            return [_deserialize(item) for item in response.get("Items", [])]
        except ClientError as e:
            logger.error(
                f"DynamoDB get_trips_by_member error: {e.response['Error']['Message']}"
            )
            raise

    async def delete_trip(self, trip_id: str) -> None:
        """Soft-delete by setting status to 'cancelled'."""
        await self.update_trip_fields(
            trip_id,
            {"status": "cancelled", "deleted_at": datetime.utcnow().isoformat()},
        )

    async def list_active_trips(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan for active trips (use sparingly - paginate for production)."""
        try:
            response = self._table.scan(
                FilterExpression=Attr("status").eq("active"),
                Limit=limit,
            )
            return [_deserialize(item) for item in response.get("Items", [])]
        except ClientError as e:
            logger.error(
                f"DynamoDB list_active_trips error: {e.response['Error']['Message']}"
            )
            raise

    async def append_expense(
        self, trip_id: str, expense: Dict[str, Any]
    ) -> None:
        """Append an expense to the trip's expense list."""
        try:
            self._table.update_item(
                Key={"trip_id": trip_id},
                UpdateExpression="SET expenses = list_append(if_not_exists(expenses, :empty), :expense), "
                                 "total_spent = if_not_exists(total_spent, :zero) + :amount, "
                                 "updated_at = :updated_at",
                ExpressionAttributeValues={
                    ":expense": [_serialize(expense)],
                    ":empty": [],
                    ":zero": Decimal("0"),
                    ":amount": Decimal(str(expense.get("total_amount", 0))),
                    ":updated_at": datetime.utcnow().isoformat(),
                },
            )
        except ClientError as e:
            logger.error(
                f"DynamoDB append_expense error: {e.response['Error']['Message']}"
            )
            raise

    async def update_member_location(
        self, trip_id: str, user_id: str, location: Dict[str, Any]
    ) -> None:
        """Update a member's location in the trip state."""
        try:
            # Fetch existing locations, update the user's entry
            trip = await self.get_trip(trip_id)
            if not trip:
                return

            locations = trip.get("member_locations", [])
            updated = False
            for i, loc in enumerate(locations):
                if loc.get("user_id") == user_id:
                    locations[i] = location
                    updated = True
                    break
            if not updated:
                locations.append(location)

            await self.update_trip_fields(trip_id, {"member_locations": locations})
        except Exception as e:
            logger.error(f"update_member_location error: {e}")
            raise


# Module-level singleton
_dynamodb_client: Optional[DynamoDBClient] = None


def get_dynamodb_client() -> DynamoDBClient:
    """Get or create DynamoDB client singleton."""
    global _dynamodb_client
    if _dynamodb_client is None:
        _dynamodb_client = DynamoDBClient()
    return _dynamodb_client
