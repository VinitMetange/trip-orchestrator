"""Razorpay payment integration for TripOrchestrator.
Handles payment links, UPI splits, and settlement tracking.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import razorpay

from src.utils.logger import get_logger
from src.utils.config import settings

logger = get_logger(__name__)

RAZORPAY_BASE = "https://api.razorpay.com/v1"


class RazorpayClient:
    """Production Razorpay client with payment links and UPI splits."""

    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

    async def create_payment_link(
        self,
        amount: float,
        description: str,
        payer_name: str,
        payer_contact: str,
        payer_email: str = "",
        reference_id: str = "",
        expire_by: int = 0,
    ) -> Dict[str, Any]:
        """Create a Razorpay payment link for expense collection."""
        try:
            payload = {
                "amount": int(amount * 100),  # paise
                "currency": "INR",
                "accept_partial": False,
                "description": description,
                "reference_id": reference_id or str(uuid.uuid4()),
                "customer": {
                    "name": payer_name,
                    "contact": payer_contact,
                },
                "notify": {"sms": True, "email": bool(payer_email)},
                "reminder_enable": True,
                "callback_url": f"{settings.BASE_URL}/webhooks/razorpay",
                "callback_method": "get",
            }
            if expire_by:
                payload["expire_by"] = expire_by
            if payer_email:
                payload["customer"]["email"] = payer_email

            link = self.client.payment_link.create(payload)
            logger.info(f"Payment link created: {link['id']} for {payer_name}")
            return {
                "link_id": link["id"],
                "short_url": link["short_url"],
                "amount": amount,
                "status": link["status"],
                "reference_id": link["reference_id"],
            }
        except Exception as e:
            logger.error(f"Create payment link error: {e}")
            raise

    async def create_group_expense_links(
        self,
        expense_id: str,
        total_amount: float,
        description: str,
        splits: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Create individual payment links for each person in a group expense."""
        results = []
        for split in splits:
            if split.get("share", 0) <= 0:
                continue
            try:
                link = await self.create_payment_link(
                    amount=split["share"],
                    description=f"{description} - Your share",
                    payer_name=split["name"],
                    payer_contact=split["phone"],
                    payer_email=split.get("email", ""),
                    reference_id=f"{expense_id}_{split['user_id']}",
                )
                results.append({
                    "user_id": split["user_id"],
                    "name": split["name"],
                    **link,
                })
            except Exception as e:
                logger.error(f"Failed to create link for {split['name']}: {e}")
                results.append({
                    "user_id": split["user_id"],
                    "name": split["name"],
                    "error": str(e),
                })
        return results

    async def get_payment_link_status(self, link_id: str) -> Dict[str, Any]:
        """Fetch current status of a payment link."""
        try:
            link = self.client.payment_link.fetch(link_id)
            return {
                "link_id": link_id,
                "status": link["status"],
                "amount_paid": link.get("amount_paid", 0) / 100,
                "payments": link.get("payments", []),
            }
        except Exception as e:
            logger.error(f"Fetch payment link error: {e}")
            raise

    async def get_expense_settlement_status(
        self, expense_id: str, splits: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check payment status for all splits of an expense."""
        statuses = []
        total_paid = 0.0
        total_pending = 0.0

        for split in splits:
            link_id = split.get("link_id")
            if not link_id:
                continue
            status = await self.get_payment_link_status(link_id)
            paid = status["status"] == "paid"
            if paid:
                total_paid += split["share"]
            else:
                total_pending += split["share"]
            statuses.append({
                "user_id": split["user_id"],
                "name": split["name"],
                "share": split["share"],
                "paid": paid,
                "payment_link": split.get("short_url", ""),
            })

        return {
            "expense_id": expense_id,
            "total_paid": total_paid,
            "total_pending": total_pending,
            "fully_settled": total_pending == 0,
            "splits": statuses,
        }

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Razorpay webhook HMAC signature."""
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_webhook_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process Razorpay webhook events."""
        event_type = event.get("event")
        payload = event.get("payload", {})

        if event_type == "payment_link.paid":
            payment_link = payload.get("payment_link", {}).get("entity", {})
            payment = payload.get("payment", {}).get("entity", {})
            logger.info(
                f"Payment received: link={payment_link.get('id')} "
                f"amount={payment.get('amount', 0)/100} INR"
            )
            return {
                "event": "payment_received",
                "link_id": payment_link.get("id"),
                "reference_id": payment_link.get("reference_id"),
                "amount": payment.get("amount", 0) / 100,
                "payment_id": payment.get("id"),
                "payer_contact": payment.get("contact"),
                "paid_at": datetime.utcfromtimestamp(
                    payment.get("created_at", 0)
                ).isoformat(),
            }

        elif event_type == "payment_link.cancelled":
            payment_link = payload.get("payment_link", {}).get("entity", {})
            return {
                "event": "payment_cancelled",
                "link_id": payment_link.get("id"),
                "reference_id": payment_link.get("reference_id"),
            }

        logger.debug(f"Unhandled Razorpay event: {event_type}")
        return {"event": event_type, "status": "ignored"}

    async def send_payment_reminder(
        self, link_id: str, payer_contact: str
    ) -> bool:
        """Resend payment reminder for an unpaid link."""
        try:
            self.client.payment_link.notifyBy(link_id, "sms")
            logger.info(f"Reminder sent for link {link_id} to {payer_contact}")
            return True
        except Exception as e:
            logger.error(f"Reminder error: {e}")
            return False

    async def create_refund(
        self, payment_id: str, amount: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create a refund for a payment."""
        try:
            payload: Dict[str, Any] = {}
            if amount:
                payload["amount"] = int(amount * 100)
            refund = self.client.payment.refund(payment_id, payload)
            logger.info(f"Refund created: {refund['id']} for payment {payment_id}")
            return {
                "refund_id": refund["id"],
                "payment_id": payment_id,
                "amount": refund["amount"] / 100,
                "status": refund["status"],
            }
        except Exception as e:
            logger.error(f"Refund error: {e}")
            raise
