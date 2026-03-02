# 🚗 TripOrchestrator

Agentic AI WhatsApp Companion for Group Trip Management. A production-grade multi-agent system built on AWS Bedrock + LangGraph.

## 🌟 Key Features

- **Multi-Agent Coordination**: Supervisor-led architecture routing to specialized agents (Planner, Expense, Tracker, Music, Insights).
- **OCR Expense Management**: Capture receipts via WhatsApp, parse with Gemini Vision, and calculate split balances automatically.
- **Smart Itineraries**: Context-aware travel planning with weather and route optimization.
- **Live Tracking**: Real-time group location sharing and ETA calculation.
- **FinTech Integration**: Instant UPI payment links via Razorpay for expense settlement.
- **Entertainment**: Group Spotify playlist management.

## 🛠️ Tech Stack

- **AI Framework**: LangGraph, LangChain
- **LLMs**: AWS Bedrock (Claude 3.5 Sonnet), Google Gemini Pro Vision (OCR)
- **Database**: Amazon DynamoDB (State management & Persistence)
- **Infrastructure**: Terraform, AWS (Lambda, Bedrock, DynamoDB)
- **Integrations**: WhatsApp Business API, Razorpay, Spotify, Google Maps

## 🧪 Testing

The project includes a comprehensive test suite covering all critical paths:

```bash
# Run all tests
pytest tests/

# Test specific components
pytest tests/test_ocr.py        # Receipt parsing & splitting
pytest tests/test_whatsapp.py   # Messaging integration
pytest tests/test_expense_agent.py # Money logic
pytest tests/test_dynamodb.py   # Data layer
pytest tests/test_orchestrator.py # AI Routing
```

## 🚀 Deployment

1. **Infrastructure**: Deploy AWS resources using Terraform in `infrastructure/terraform/`.
2. **Environment**: Configure `.env` with API keys (WhatsApp, Bedrock, Razorpay, Spotify).
3. **App**: Deploy the FastAPI application to AWS Lambda or EKS.
