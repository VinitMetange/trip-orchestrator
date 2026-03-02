"""
TripOrchestrator - Main Application Entry Point
Production-grade FastAPI application for WhatsApp Agentic AI
"""
import os
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

import boto3
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from src.handlers.webhook_handler import WebhookHandler
from src.utils.bedrock_client import BedrockClient
from src.utils.logger import setup_logger
from src.models.trip_state import TripStateManager

logger = setup_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info("TripOrchestrator starting up...")
    # Initialize DynamoDB tables
    state_manager = TripStateManager()
    await state_manager.initialize()
    # Warm up Bedrock client
    bedrock = BedrockClient()
    logger.info("TripOrchestrator ready!")
    yield
    logger.info("TripOrchestrator shutting down...")

app = FastAPI(
    title="TripOrchestrator API",
    description="Agentic AI WhatsApp Companion for Group Trip Management",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
)

# Security middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://graph.facebook.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Initialize handlers
webhook_handler = WebhookHandler()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "service": "TripOrchestrator"
    }

@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    WhatsApp webhook verification
    GET request from Meta to verify the endpoint
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN")

    if mode == "subscribe" and token == verify_token:
        logger.info("Webhook verified successfully")
        return int(challenge)
    
    raise HTTPException(status_code=403, detail="Webhook verification failed")

@app.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Handle incoming WhatsApp messages
    Process messages asynchronously for fast response
    """
    try:
        body = await request.json()
        logger.info(f"Received webhook: {json.dumps(body, indent=2)[:500]}")

        # Validate WhatsApp webhook structure
        if body.get("object") != "whatsapp_business_account":
            raise HTTPException(status_code=400, detail="Invalid webhook object")

        # Process message in background (async - return 200 immediately)
        background_tasks.add_task(
            webhook_handler.process_message,
            body
        )

        return JSONResponse(
            content={"status": "received"},
            status_code=200
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        # Always return 200 to WhatsApp to avoid retry storms
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=200
        )

@app.post("/test/message")
async def test_message(request: Request):
    """
    Test endpoint for local development
    Simulate WhatsApp messages without actual webhook
    """
    if os.getenv("ENV") == "production":
        raise HTTPException(status_code=404)
    
    body = await request.json()
    response = await webhook_handler.process_test_message(
        phone_number=body.get("phone_number", "+919999999999"),
        message=body.get("message", ""),
        group_id=body.get("group_id", "test_group_1")
    )
    return response

# AWS Lambda handler
handler = Mangum(app, lifespan="off")
