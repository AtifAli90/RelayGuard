from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def fixed_client(tmp_path):
    app = create_app(tmp_path / "fixed.sqlite3")
    with TestClient(app) as client:
        yield client
