"""Pytest configuration and fixtures for RelayGuard PostgreSQL test suite."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from app.config import get_database_url
from app.main import create_app
from app.baseline import create_baseline_app
from app.storage import initialize_database, truncate_tables, connect


@pytest.fixture(scope="session")
def db_url() -> str:
    """Ensure PostgreSQL is accessible and schema is initialized for the test session."""
    url = get_database_url()
    try:
        # Verify connection and initialize tables
        initialize_database(url)
    except Exception as exc:
        pytest.fail(
            f"Failed to connect to PostgreSQL at '{url}': {exc}\n"
            "Ensure PostgreSQL is running (e.g. 'docker compose up -d --wait db') "
            "and DATABASE_URL is configured in .env or environment.",
            pytrace=False,
        )
    return url


@pytest.fixture(autouse=True)
def clean_database(db_url: str):
    """Truncate tables before each test to guarantee absolute test repeatability."""
    truncate_tables(db_url)
    yield
    truncate_tables(db_url)


@pytest.fixture
def fixed_client(db_url: str):
    """FastAPI TestClient configured with the fixed replay-safe app."""
    app = create_app(db_url)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def baseline_client(db_url: str):
    """FastAPI TestClient configured with the intentionally defective baseline app."""
    app = create_baseline_app(db_url)
    with TestClient(app) as client:
        yield client
