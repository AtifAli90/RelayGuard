"""RelayGuard configuration and environment settings."""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv_if_present() -> None:
    """Simple parser for local .env file to avoid external dotenv dependencies."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.is_file():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and "=" in stripped:
                        key, val = stripped.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
        except OSError:
            pass


_load_dotenv_if_present()


def get_database_url() -> str:
    """Retrieve the PostgreSQL connection URL or fail fast with actionable guidance."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Please provide a PostgreSQL connection URL via the "
            "DATABASE_URL environment variable or in a local .env file. "
            "Example: postgresql://relayguard:relayguard_dev_password@localhost:5434/relayguard "
            "(Run 'docker compose up -d --wait db' to start the local development database)."
        )
    return url
