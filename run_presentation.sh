#!/usr/bin/env bash
set -e

echo "================================================================="
echo "   RELAYGUARD -- LIVE PRESENTATION & DEMONSTRATION RUNNER       "
echo "================================================================="

# 1. Verify PostgreSQL Database
echo -e "\n[1/3] Ensuring PostgreSQL Database is accessible..."
docker compose up -d --wait db 2>/dev/null || true

# 2. Run Test Suite
echo -e "\n[2/3] Running Automated Test Suite..."
python -m pytest -q

# 3. Run Live Interactive Demo
echo -e "\n[3/3] Running Live Concurrency & Replay Protection Demo..."
python -m scripts.demo_live

# 4. Launch Local Swagger UI & Server
echo "================================================================="
echo "Launching local FastAPI service with Swagger UI at: "
echo "http://127.0.0.1:8000/docs"
echo "Press Ctrl+C to terminate the server when done."
echo "================================================================="

uvicorn app.main:app --reload
