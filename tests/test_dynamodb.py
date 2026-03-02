"""Tests for DynamoDB data access layer."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from botocore.exceptions import ClientError

from src.utils.dynamodb import DynamoDBClient, _serialize, _deserialize, get_dynamodb_client


@pytest.fixture
def mock_table():
    """Create mock DynamoDB table."""
    return MagicMock()


@pytest.fixture
def dynamodb_client(mock_table):
    """Create DynamoDB client with mocked AWS resources."""
    with patch("src.utils.dynamodb.boto3.resource") as mock_resource:
        mock_resource.return_value.Table.return_value = mock_table
        client = DynamoDBClient()
        client._table = mock_table
        return client


# ============================================================
# Serialization Tests
# ============================================================

def test_serialize_float():
    """Test float serialization to Decimal."""
    result = _serialize(100.5)
    assert isinstance(result, Decimal)
    assert result == Decimal("100.5")


def test_serialize_dict():
    """Test dict serialization recursively."""
    data = {"amount": 100.5, "count": 3}
    result = _serialize(data)
    assert isinstance(result["amount"], Decimal)
    assert result["count"] == 3  # int stays int


def test_serialize_list():
    """Test list serialization recursively."""
    data = [100.5, 200.0, "string"]
    result = _serialize(data)
    assert isinstance(result[0], Decimal)
    assert isinstance(result[1], Decimal)
    assert result[2] == "string"


def test_serialize_string_unchanged():
    """Test that strings pass through unchanged."""
    result = _serialize("test_string")
    assert result == "test_string"


def test_deserialize_decimal():
    """Test Decimal deserialization to float."""
    result = _deserialize(Decimal("99.99"))
    assert isinstance(result, float)
    assert result == 99.99


def test_deserialize_dict():
    """Test dict deserialization recursively."""
    data = {"price": Decimal("50.0"), "name": "Test"}
    result = _deserialize(data)
    assert isinstance(result["price"], float)
    assert result["name"] == "Test"


def test_deserialize_list():
    """Test list deserialization recursively."""
    data = [Decimal("10.0"), Decimal("20.0"), "item"]
    result = _deserialize(data)
    assert result[0] == 10.0
    assert result[1] == 20.0
    assert result[2] == "item"


def test_serialize_deserialize_roundtrip():
    """Test that serialize/deserialize is a roundtrip."""
    original = {
        "total_amount": 1800.0,
        "items": [100.0, 200.0, 300.0],
        "name": "Test Trip",
        "count": 3
    }
    
    serialized = _serialize(original)
    deserialized = _deserialize(serialized)
    
    assert deserialized["total_amount"] == original["total_amount"]
    assert deserialized["items"] == original["items"]
    assert deserialized["name"] == original["name"]


# ============================================================
# DynamoDBClient Tests
# ============================================================

@pytest.mark.asyncio
async def test_get_trip_success(dynamodb_client, mock_table, sample_trip_data):
    """Test successful trip retrieval."""
    mock_table.get_item.return_value = {
        "Item": {**sample_trip_data, "total_spent": Decimal("0.0")}
    }
    
    result = await dynamodb_client.get_trip("trip_test_001")
    
    assert result is not None
    assert result["trip_id"] == "trip_test_001"
    mock_table.get_item.assert_called_once_with(
        Key={"trip_id": "trip_test_001"},
        ConsistentRead=True
    )


@pytest.mark.asyncio
async def test_get_trip_not_found(dynamodb_client, mock_table):
    """Test trip retrieval when trip doesn't exist."""
    mock_table.get_item.return_value = {}
    
    result = await dynamodb_client.get_trip("nonexistent_trip")
    
    assert result is None


@pytest.mark.asyncio
async def test_get_trip_client_error(dynamodb_client, mock_table):
    """Test trip retrieval raises on ClientError."""
    mock_table.get_item.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}},
        "GetItem"
    )
    
    with pytest.raises(ClientError):
        await dynamodb_client.get_trip("trip_001")


@pytest.mark.asyncio
async def test_save_trip(dynamodb_client, mock_table, sample_trip_data):
    """Test saving a trip to DynamoDB."""
    mock_table.put_item.return_value = {}
    
    await dynamodb_client.save_trip(sample_trip_data)
    
    assert mock_table.put_item.called
    call_args = mock_table.put_item.call_args[1]
    assert "Item" in call_args
    assert "updated_at" in call_args["Item"]


@pytest.mark.asyncio
async def test_save_trip_client_error(dynamodb_client, mock_table, sample_trip_data):
    """Test save_trip raises on ClientError."""
    mock_table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "Throttled"}},
        "PutItem"
    )
    
    with pytest.raises(ClientError):
        await dynamodb_client.save_trip(sample_trip_data)


@pytest.mark.asyncio
async def test_update_trip_fields(dynamodb_client, mock_table):
    """Test partial update of trip fields."""
    mock_table.update_item.return_value = {}
    
    await dynamodb_client.update_trip_fields(
        trip_id="trip_001",
        updates={"status": "active", "destination": "Goa"}
    )
    
    assert mock_table.update_item.called
    call_args = mock_table.update_item.call_args[1]
    assert call_args["Key"] == {"trip_id": "trip_001"}
    # Check that updated_at is included
    assert "#updated_at" in call_args["ExpressionAttributeNames"].values() or \
           "updated_at" in str(call_args["ExpressionAttributeNames"])


@pytest.mark.asyncio
async def test_delete_trip(dynamodb_client, mock_table):
    """Test soft-delete (sets status to cancelled)."""
    mock_table.update_item.return_value = {}
    
    await dynamodb_client.delete_trip("trip_001")
    
    assert mock_table.update_item.called
    # Should set status=cancelled via update_trip_fields
    call_args = mock_table.update_item.call_args[1]
    values = call_args["ExpressionAttributeValues"]
    assert "cancelled" in values.values()


@pytest.mark.asyncio
async def test_get_trips_by_member(dynamodb_client, mock_table, sample_trip_data):
    """Test querying trips by member."""
    mock_table.query.return_value = {
        "Items": [sample_trip_data]
    }
    
    results = await dynamodb_client.get_trips_by_member("user_001")
    
    assert len(results) == 1
    assert results[0]["trip_id"] == "trip_test_001"
    mock_table.query.assert_called_once()


@pytest.mark.asyncio
async def test_list_active_trips(dynamodb_client, mock_table, sample_trip_data):
    """Test listing active trips."""
    active_trip = {**sample_trip_data, "status": "active"}
    mock_table.scan.return_value = {
        "Items": [active_trip]
    }
    
    results = await dynamodb_client.list_active_trips()
    
    assert len(results) == 1
    mock_table.scan.assert_called_once()


@pytest.mark.asyncio
async def test_append_expense(dynamodb_client, mock_table):
    """Test appending expense to trip."""
    mock_table.update_item.return_value = {}
    
    expense = {
        "amount": 1800.0,
        "total_amount": 1800.0,
        "vendor": "Taj Restaurant",
        "category": "food"
    }
    
    await dynamodb_client.append_expense("trip_001", expense)
    
    assert mock_table.update_item.called
    call_args = mock_table.update_item.call_args[1]
    assert call_args["Key"] == {"trip_id": "trip_001"}
    # Verify expense list append
    assert "list_append" in call_args["UpdateExpression"]


@pytest.mark.asyncio
async def test_update_member_location(dynamodb_client, mock_table, sample_trip_data):
    """Test updating member location."""
    # Set up get_trip to return trip with no existing locations
    trip_with_location = {**sample_trip_data, "member_locations": []}
    mock_table.get_item.return_value = {"Item": trip_with_location}
    mock_table.update_item.return_value = {}
    
    location = {
        "user_id": "user_001",
        "lat": 15.2993,
        "lng": 74.1240,
        "timestamp": "2025-01-15T10:00:00"
    }
    
    await dynamodb_client.update_member_location(
        trip_id="trip_test_001",
        user_id="user_001",
        location=location
    )
    
    # update_item should be called to save the updated locations
    assert mock_table.update_item.called


@pytest.mark.asyncio
async def test_update_member_location_updates_existing(dynamodb_client, mock_table, sample_trip_data):
    """Test updating an existing member's location."""
    existing_location = {
        "user_id": "user_001",
        "lat": 15.0,
        "lng": 74.0,
        "timestamp": "2025-01-15T09:00:00"
    }
    trip_with_location = {**sample_trip_data, "member_locations": [existing_location]}
    mock_table.get_item.return_value = {"Item": trip_with_location}
    mock_table.update_item.return_value = {}
    
    new_location = {
        "user_id": "user_001",
        "lat": 15.2993,
        "lng": 74.1240,
        "timestamp": "2025-01-15T10:00:00"
    }
    
    await dynamodb_client.update_member_location(
        trip_id="trip_test_001",
        user_id="user_001",
        location=new_location
    )
    
    # Should update (not append) the existing location
    assert mock_table.update_item.called


@pytest.mark.asyncio
async def test_update_member_location_trip_not_found(dynamodb_client, mock_table):
    """Test updating location when trip doesn't exist."""
    mock_table.get_item.return_value = {}  # No item found
    
    location = {"user_id": "user_001", "lat": 15.0, "lng": 74.0}
    
    # Should not raise, just return early
    await dynamodb_client.update_member_location(
        trip_id="nonexistent",
        user_id="user_001",
        location=location
    )
    
    # update_item should NOT be called
    mock_table.update_item.assert_not_called()


def test_get_dynamodb_client_singleton():
    """Test that get_dynamodb_client returns singleton."""
    import src.utils.dynamodb as dynamodb_module
    # Reset singleton
    dynamodb_module._dynamodb_client = None
    
    with patch("src.utils.dynamodb.boto3.resource") as mock_resource:
        mock_resource.return_value.Table.return_value = MagicMock()
        
        client1 = get_dynamodb_client()
        client2 = get_dynamodb_client()
        
        assert client1 is client2  # Same instance
        assert mock_resource.call_count == 1  # Only created once
