# RelayGuard One-Command Presentation Launcher (Windows PowerShell)
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "   RELAYGUARD -- LIVE PRESENTATION & DEMONSTRATION RUNNER       " -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Verify PostgreSQL Database
Write-Host "`n[1/3] Ensuring PostgreSQL Database is accessible..." -ForegroundColor Green
docker compose up -d --wait db 2>$null

# 2. Run Test Suite
Write-Host "`n[2/3] Running Automated Test Suite..." -ForegroundColor Green
python -m pytest -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tests failed. Please verify PostgreSQL connection." -ForegroundColor Red
    exit 1
}

# 3. Run Live Interactive Demo
Write-Host "`n[3/3] Running Live Concurrency & Replay Protection Demo..." -ForegroundColor Green
python -m scripts.demo_live

# 4. Launch Local Swagger UI & Server
Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "Launching local FastAPI service with Swagger UI at: " -ForegroundColor Yellow
Write-Host "http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "Press Ctrl+C to terminate the server when done." -ForegroundColor Gray
Write-Host "=================================================================" -ForegroundColor Cyan

Start-Process "http://127.0.0.1:8000/docs"
uvicorn app.main:app --reload
