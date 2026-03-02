"""Pydantic models for TripOrchestrator state management.
Defines all data structures used across agents and DynamoDB.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TripStatus(str, Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MemberRole(str, Enum):
    ORGANIZER = "organizer"
    MEMBER = "member"
    VIEWER = "viewer"


class ExpenseCategory(str, Enum):
    FOOD = "Food"
    TRANSPORT = "Transport"
    ACCOMMODATION = "Accommodation"
    ENTERTAINMENT = "Entertainment"
    SHOPPING = "Shopping"
    OTHER = "Other"


class SplitType(str, Enum):
    EQUAL = "equal"
    CUSTOM = "custom"
    PERCENTAGE = "percentage"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class TrafficCondition(str, Enum):
    CLEAR = "Clear"
    MODERATE = "Moderate"
    HEAVY = "Heavy - consider alternatives"


# ─── Member & Trip ───────────────────────────────────────────────────────────

class TripMember(BaseModel):
    user_id: str
    name: str
    phone: str  # WhatsApp number in E.164 format
    email: Optional[str] = ""
    role: MemberRole = MemberRole.MEMBER
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class TripStop(BaseModel):
    place_name: str
    address: str
    lat: float = 0.0
    lng: float = 0.0
    arrival_time: Optional[str] = ""
    departure_time: Optional[str] = ""
    notes: str = ""


class TripItinerary(BaseModel):
    day: int
    date: Optional[str] = ""
    stops: List[TripStop] = []
    activities: List[str] = []
    accommodation: Optional[str] = ""
    estimated_cost: float = 0.0


# ─── Expense ─────────────────────────────────────────────────────────────────

class ExpenseSplit(BaseModel):
    user_id: str
    name: str
    phone: str
    share: float
    paid: bool = False
    payment_link_id: Optional[str] = ""
    payment_link_url: Optional[str] = ""
    payment_id: Optional[str] = ""
    paid_at: Optional[datetime] = None


class Expense(BaseModel):
    expense_id: str
    trip_id: str
    description: str
    total_amount: float
    currency: str = "INR"
    category: ExpenseCategory = ExpenseCategory.OTHER
    paid_by_user_id: str
    paid_by_name: str
    split_type: SplitType = SplitType.EQUAL
    splits: List[ExpenseSplit] = []
    receipt_url: Optional[str] = ""
    merchant_name: Optional[str] = ""
    items: List[Dict[str, Any]] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    fully_settled: bool = False
    notes: str = ""


# ─── Location ─────────────────────────────────────────────────────────────────

class MemberLocation(BaseModel):
    user_id: str
    name: str
    lat: float
    lng: float
    accuracy: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    battery_level: Optional[int] = None


class SOSAlert(BaseModel):
    alert_id: str
    trip_id: str
    user_id: str
    user_name: str
    lat: float
    lng: float
    message: str = "SOS - Need immediate help!"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolved_at: Optional[datetime] = None


# ─── Music ───────────────────────────────────────────────────────────────────

class MusicVote(BaseModel):
    track_id: str
    track_name: str
    artist: str
    suggested_by: str
    votes_up: List[str] = []  # user_ids
    votes_down: List[str] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MusicSession(BaseModel):
    session_id: str
    trip_id: str
    playlist_id: Optional[str] = ""
    playlist_url: Optional[str] = ""
    current_track: Optional[str] = ""
    queue: List[MusicVote] = []
    mood: str = "upbeat"
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Agent Messages ───────────────────────────────────────────────────────────

class AgentMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str
    agent: Optional[str] = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = {}


# ─── Main Trip State ──────────────────────────────────────────────────────────

class TripState(BaseModel):
    """Central state object for a trip - stored in DynamoDB."""
    trip_id: str
    trip_name: str
    status: TripStatus = TripStatus.PLANNING
    organizer_id: str
    members: List[TripMember] = []
    destination: str = ""
    start_date: Optional[str] = ""
    end_date: Optional[str] = ""
    budget_per_person: float = 0.0
    total_budget: float = 0.0
    itinerary: List[TripItinerary] = []
    expenses: List[Expense] = []
    total_spent: float = 0.0
    member_locations: List[MemberLocation] = []
    sos_alerts: List[SOSAlert] = []
    music_session: Optional[MusicSession] = None
    conversation_history: List[AgentMessage] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    whatsapp_group_id: Optional[str] = ""
    metadata: Dict[str, Any] = {}

    def get_member(self, user_id: str) -> Optional[TripMember]:
        """Get member by user_id."""
        return next((m for m in self.members if m.user_id == user_id), None)

    def get_active_members(self) -> List[TripMember]:
        """Return only active members."""
        return [m for m in self.members if m.is_active]

    def total_expenses_by_category(self) -> Dict[str, float]:
        """Aggregate expenses by category."""
        result: Dict[str, float] = {}
        for expense in self.expenses:
            cat = expense.category.value
            result[cat] = result.get(cat, 0) + expense.total_amount
        return result

    def get_unsettled_expenses(self) -> List[Expense]:
        """Return expenses with pending payments."""
        return [e for e in self.expenses if not e.fully_settled]


# ─── Request/Response Schemas ─────────────────────────────────────────────────

class WhatsAppWebhookPayload(BaseModel):
    object: str
    entry: List[Dict[str, Any]]


class IncomingMessage(BaseModel):
    trip_id: Optional[str] = ""
    user_id: str
    user_name: str
    phone: str
    message_type: str  # text | image | audio | location | document
    text: Optional[str] = ""
    media_id: Optional[str] = ""
    location: Optional[Dict[str, float]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    wa_message_id: str = ""


class AgentResponse(BaseModel):
    message: str
    agent_used: str
    trip_id: Optional[str] = ""
    actions_taken: List[str] = []
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None
