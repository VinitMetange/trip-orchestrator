"""Tests for TripOrchestrator Pydantic models."""
from datetime import datetime
from unittest.mock import patch

import pytest

from src.models.trip_state import (
    AgentResponse,
    Expense,
    ExpenseCategory,
    ExpenseSplit,
    IncomingMessage,
    MemberLocation,
    MemberRole,
    MusicSession,
    MusicVote,
    PaymentStatus,
    SOSAlert,
    SplitType,
    TripItinerary,
    TripMember,
    TripState,
    TripStatus,
    TripStop,
)


class TestTripMember:
    def test_create_member(self):
        member = TripMember(
            user_id="user_001",
            name="Vikas Shah",
            phone="+919876543210",
            email="vikas@example.com",
            role=MemberRole.ORGANIZER,
        )
        assert member.user_id == "user_001"
        assert member.name == "Vikas Shah"
        assert member.role == MemberRole.ORGANIZER
        assert member.is_active is True

    def test_default_role_is_member(self):
        member = TripMember(
            user_id="u2",
            name="Priya",
            phone="+919876543211",
        )
        assert member.role == MemberRole.MEMBER


class TestExpense:
    def test_create_expense(self):
        split = ExpenseSplit(
            user_id="u1",
            name="Alice",
            phone="+919876543210",
            share=500.0,
        )
        expense = Expense(
            expense_id="exp_001",
            trip_id="trip_001",
            description="Dinner at Taj",
            total_amount=1500.0,
            category=ExpenseCategory.FOOD,
            paid_by_user_id="u1",
            paid_by_name="Alice",
            splits=[split],
        )
        assert expense.total_amount == 1500.0
        assert expense.category == ExpenseCategory.FOOD
        assert len(expense.splits) == 1
        assert expense.fully_settled is False


class TestTripState:
    @pytest.fixture
    def trip(self):
        organizer = TripMember(
            user_id="organizer_001",
            name="Raj Kumar",
            phone="+919876543210",
            role=MemberRole.ORGANIZER,
        )
        member1 = TripMember(
            user_id="member_001",
            name="Priya Singh",
            phone="+919876543211",
        )
        return TripState(
            trip_id="trip_001",
            trip_name="Goa Trip 2025",
            organizer_id="organizer_001",
            members=[organizer, member1],
            destination="Goa",
            budget_per_person=10000.0,
        )

    def test_create_trip(self, trip):
        assert trip.trip_id == "trip_001"
        assert trip.trip_name == "Goa Trip 2025"
        assert trip.status == TripStatus.PLANNING
        assert len(trip.members) == 2

    def test_get_member(self, trip):
        member = trip.get_member("organizer_001")
        assert member is not None
        assert member.name == "Raj Kumar"

    def test_get_member_not_found(self, trip):
        member = trip.get_member("nonexistent")
        assert member is None

    def test_get_active_members(self, trip):
        active = trip.get_active_members()
        assert len(active) == 2

        # Deactivate one member
        trip.members[1].is_active = False
        active = trip.get_active_members()
        assert len(active) == 1

    def test_total_expenses_by_category(self, trip):
        food_expense = Expense(
            expense_id="exp_001",
            trip_id="trip_001",
            description="Lunch",
            total_amount=600.0,
            category=ExpenseCategory.FOOD,
            paid_by_user_id="organizer_001",
            paid_by_name="Raj Kumar",
        )
        transport_expense = Expense(
            expense_id="exp_002",
            trip_id="trip_001",
            description="Cab",
            total_amount=300.0,
            category=ExpenseCategory.TRANSPORT,
            paid_by_user_id="organizer_001",
            paid_by_name="Raj Kumar",
        )
        trip.expenses = [food_expense, transport_expense]
        by_category = trip.total_expenses_by_category()
        assert by_category["Food"] == 600.0
        assert by_category["Transport"] == 300.0

    def test_get_unsettled_expenses(self, trip):
        settled = Expense(
            expense_id="exp_001",
            trip_id="trip_001",
            description="Settled",
            total_amount=100.0,
            category=ExpenseCategory.OTHER,
            paid_by_user_id="organizer_001",
            paid_by_name="Raj Kumar",
            fully_settled=True,
        )
        unsettled = Expense(
            expense_id="exp_002",
            trip_id="trip_001",
            description="Unsettled",
            total_amount=200.0,
            category=ExpenseCategory.OTHER,
            paid_by_user_id="organizer_001",
            paid_by_name="Raj Kumar",
            fully_settled=False,
        )
        trip.expenses = [settled, unsettled]
        unsettled_list = trip.get_unsettled_expenses()
        assert len(unsettled_list) == 1
        assert unsettled_list[0].expense_id == "exp_002"


class TestSOSAlert:
    def test_create_sos_alert(self):
        alert = SOSAlert(
            alert_id="sos_001",
            trip_id="trip_001",
            user_id="user_001",
            user_name="Alice",
            lat=15.2993,
            lng=74.1240,
        )
        assert alert.resolved is False
        assert alert.message == "SOS - Need immediate help!"
        assert alert.lat == 15.2993


class TestIncomingMessage:
    def test_text_message(self):
        msg = IncomingMessage(
            user_id="user_001",
            user_name="Alice",
            phone="+919876543210",
            message_type="text",
            text="Plan a trip to Goa",
            wa_message_id="wamid_001",
        )
        assert msg.message_type == "text"
        assert msg.text == "Plan a trip to Goa"

    def test_image_message(self):
        msg = IncomingMessage(
            user_id="user_001",
            user_name="Alice",
            phone="+919876543210",
            message_type="image",
            media_id="media_001",
            wa_message_id="wamid_002",
        )
        assert msg.message_type == "image"
        assert msg.media_id == "media_001"
