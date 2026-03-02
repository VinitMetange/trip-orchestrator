# TripOrchestrator - Production Dockerfile
# Multi-stage build for minimal Lambda container image

# ─── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --target /build/packages -r requirements.txt

# ─── Stage 2: Production Image ───────────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.12 AS production

# Copy installed packages from builder
COPY --from=builder /build/packages ${LAMBDA_TASK_ROOT}

# Copy application source
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# Set Lambda handler
CMD ["src.main.handler"]

# ─── Labels ────────────────────────────────────────────────────────────────────
LABEL org.opencontainers.image.title="TripOrchestrator"
LABEL org.opencontainers.image.description="Agentic AI WhatsApp Companion for Group Trip Management"
LABEL org.opencontainers.image.vendor="VinitMetange"
LABEL org.opencontainers.image.licenses="MIT"
