"""Tests for ExpenseAgent and expense management."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

from src.agents.expense_agent import ExpenseAgent, ExpenseEntry


@pytest.fixture
def mock_llm():
    """Create mock LLM."""
    llm = MagicMock()
    llm.invoke = MagicMock()
    return llm


@pytest.fixture
def expense_agent(mock_llm):
    """Create ExpenseAgent instance with mock dependencies."""
    with patch("src.agents.expense_agent.GeminiOCRClient"), \
         patch("src.agents.expense_agent.RazorpayClient"):
        agent = ExpenseAgent(mock_llm)
        return agent


@pytest.fixture
def sample_trip_state():
    """Sample trip state for testing."""
    return {
        "participants": ["Raj", "Priya", "Amit"],
        "balances": {},
        "expenses": []
    }


def test_expense_entry_creation():
    """Test ExpenseEntry dataclass."""
    expense = ExpenseEntry(
        amount=500.0,
        category="fuel",
        description="Petrol for trip",
        paid_by="Raj",
        split_among=["Raj", "Priya", "Amit"]
    )
    
    assert expense.amount == 500.0
    assert expense.category == "fuel"
    assert len(expense.split_among) == 3


@pytest.mark.asyncio
async def test_process_receipt_with_ocr(expense_agent, sample_trip_state):
    """Test processing receipt image with OCR."""
    expense_agent.ocr.extract_receipt = AsyncMock(return_value={
        "total_amount": 1800.0,
        "vendor": "Taj Restaurant",
        "category": "food",
        "url": "https://example.com/receipt.jpg"
    })
    
    message = "[MEDIA: https://example.com/receipt.jpg] Raj paid"
    state = {
        "messages": [MagicMock(content=message)],
        "trip_state": sample_trip_state
    }
    
    result = await expense_agent.run(state)
    
    assert "response" in result
    assert "₹1,800" in result["response"]
    assert "Taj Restaurant" in result["response"]


@pytest.mark.asyncio
async def test_parse_text_expense(expense_agent, sample_trip_state):
    """Test parsing expense from text description."""
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "amount": 300.0,
        "category": "food",
        "description": "Lunch at cafe",
        "paid_by": "Priya",
        "split_among": ["Raj", "Priya", "Amit"]
    })
    expense_agent.llm.invoke.return_value = mock_response
    
    message = "Priya paid 300 for lunch"
    state = {
        "messages": [MagicMock(content=message)],
        "trip_state": sample_trip_state
    }
    
    result = await expense_agent.run(state)
    
    assert "response" in result
    assert "₹300" in result["response"]
    assert "100/person" in result["response"]


def test_calculate_splits_equal(expense_agent):
    """Test equal split calculation."""
    expense = ExpenseEntry(
        amount=900.0,
        category="food",
        description="Dinner",
        paid_by="Raj",
        split_among=["Raj", "Priya", "Amit"]
    )
    
    participants = ["Raj", "Priya", "Amit", "Neha"]
    splits = expense_agent._calculate_splits(expense, participants)
    
    assert len(splits) == 3  # Only split among specified people
    assert splits["Raj"] == 300.0
    assert splits["Priya"] == 300.0
    assert splits["Amit"] == 300.0


def test_update_balances(expense_agent):
    """Test balance updates after expense."""
    current_balances = {
        "Raj": 0,
        "Priya": 0,
        "Amit": 0
    }
    
    expense = ExpenseEntry(
        amount=900.0,
        category="food",
        description="Dinner",
        paid_by="Raj",
        split_among=["Raj", "Priya", "Amit"]
    )
    
    splits = {
        "Raj": 300.0,
        "Priya": 300.0,
        "Amit": 300.0
    }
    
    updated = expense_agent._update_balances(current_balances, expense, splits)
    
    assert updated["Raj"] == 600.0  # Paid 900, owes 300
    assert updated["Priya"] == -300.0  # Owes 300
    assert updated["Amit"] == -300.0  # Owes 300


def test_format_expense_response(expense_agent):
    """Test expense response formatting."""
    expense = ExpenseEntry(
        amount=1200.0,
        category="fuel",
        description="Highway toll",
        paid_by="Amit",
        split_among=["Raj", "Priya", "Amit"]
    )
    
    splits = {
        "Raj": 400.0,
        "Priya": 400.0,
        "Amit": 400.0
    }
    
    balances = {
        "Amit": 800.0,
        "Raj": -400.0,
        "Priya": -400.0
    }
    
    response = expense_agent._format_expense_response(expense, splits, balances)
    
    assert "⛽" in response  # Fuel emoji
    assert "Highway toll" in response
    assert "₹1,200" in response
    assert "₹400/person" in response
    assert "Amit" in response
    assert "Raj" in response


def test_extract_media_url(expense_agent):
    """Test media URL extraction from message."""
    message = "Check this receipt [MEDIA: https://example.com/image.jpg]"
    url = expense_agent._extract_media_url(message)
    
    assert url == "https://example.com/image.jpg"


def test_extract_media_url_none(expense_agent):
    """Test message without media URL."""
    message = "Paid 500 for fuel"
    url = expense_agent._extract_media_url(message)
    
    assert url is None


def test_extract_payer(expense_agent):
    """Test payer extraction from message."""
    participants = ["Raj", "Priya", "Amit"]
    
    message = "Priya paid for lunch"
    payer = expense_agent._extract_payer(message, participants)
    
    assert payer == "Priya"


def test_extract_payer_default(expense_agent):
    """Test default payer when not found."""
    participants = ["Raj", "Priya", "Amit"]
    
    message = "Paid for lunch"
    payer = expense_agent._extract_payer(message, participants)
    
    assert payer == "me"


@pytest.mark.asyncio
async def test_generate_settlement_links(expense_agent):
    """Test UPI settlement link generation."""
    expense_agent.razorpay.create_payment_link = AsyncMock(
        return_value="https://rzp.io/l/test123"
    )
    
    balances = {
        "Raj": 600.0,  # To receive
        "Priya": -300.0,  # Owes
        "Amit": -300.0  # Owes
    }
    
    result = await expense_agent.generate_settlement_links(balances)
    
    assert "Settlement Links" in result
    assert "Priya → Raj" in result or "Amit → Raj" in result
    assert "https://rzp.io" in result


@pytest.mark.asyncio
async def test_generate_settlement_links_balanced(expense_agent):
    """Test settlement when all balanced."""
    balances = {
        "Raj": 0,
        "Priya": 0,
        "Amit": 0
    }
    
    result = await expense_agent.generate_settlement_links(balances)
    
    assert "All settled" in result
    assert "No pending payments" in result


def test_expense_categories():
    """Test that all expected categories are defined."""
    from src.agents.expense_agent import EXPENSE_CATEGORIES
    
    expected = [
        "fuel", "food", "accommodation", "tickets",
        "shopping", "transport", "emergency", "miscellaneous"
    ]
    
    for category in expected:
        assert category in EXPENSE_CATEGORIES


@pytest.mark.asyncio
async def test_handle_invalid_expense(expense_agent, sample_trip_state):
    """Test handling of invalid expense input."""
    mock_response = MagicMock()
    mock_response.content = "Invalid JSON"
    expense_agent.llm.invoke.return_value = mock_response
    
    message = "Some random text"
    state = {
        "messages": [MagicMock(content=message)],
        "trip_state": sample_trip_state
    }
    
    result = await expense_agent.run(state)
    
    assert "response" in result
    # Should ask for clarification
    assert "How much" in result["response"] or "expense" in result["response"].lower()


@pytest.mark.asyncio
async def test_multiple_expenses_tracking(expense_agent):
    """Test tracking multiple expenses in trip state."""
    trip_state = {
        "participants": ["Raj", "Priya"],
        "balances": {},
        "expenses": []
    }
    
    # First expense
    expense1 = ExpenseEntry(
        amount=400.0,
        category="food",
        description="Lunch",
        paid_by="Raj",
        split_among=["Raj", "Priya"]
    )
    
    splits1 = {"Raj": 200.0, "Priya": 200.0}
    balances1 = expense_agent._update_balances({}, expense1, splits1)
    
    # Second expense
    expense2 = ExpenseEntry(
        amount=600.0,
        category="fuel",
        description="Petrol",
        paid_by="Priya",
        split_among=["Raj", "Priya"]
    )
    
    splits2 = {"Raj": 300.0, "Priya": 300.0}
    balances2 = expense_agent._update_balances(balances1, expense2, splits2)
    
    # Check final balances
    assert balances2["Raj"] == -100.0  # Owes 100
    assert balances2["Priya"] == 100.0  # To receive 100


def test_split_rounding(expense_agent):
    """Test that splits are properly rounded."""
    expense = ExpenseEntry(
        amount=100.0,
        category="food",
        description="Test",
        paid_by="Raj",
        split_among=["Raj", "Priya", "Amit"]
    )
    
    splits = expense_agent._calculate_splits(expense, ["Raj", "Priya", "Amit"])
    
    # Should round to 2 decimal places
    for amount in splits.values():
        assert round(amount, 2) == amount


@pytest.mark.asyncio
async def test_expense_with_receipt_url(expense_agent, sample_trip_state):
    """Test expense tracking includes receipt URL."""
    expense_agent.ocr.extract_receipt = AsyncMock(return_value={
        "total_amount": 500.0,
        "vendor": "Shop",
        "category": "shopping",
        "url": "https://example.com/receipt.jpg"
    })
    
    message = "[MEDIA: https://example.com/receipt.jpg]"
    state = {
        "messages": [MagicMock(content=message)],
        "trip_state": sample_trip_state
    }
    
    result = await expense_agent.run(state)
    
    # Check that expense is added to trip state
    assert len(result["trip_state"]["expenses"]) > 0
