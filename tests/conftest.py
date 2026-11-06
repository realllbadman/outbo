import os

# Set before importing the app. These take priority over any .env file, so tests
# never touch the real database, credentials or mail account.
os.environ.update(
    DATABASE_URL="sqlite://",
    SMTP_HOST="smtp.invalid",
    SMTP_PASS="test pass word",
    ADMIN_USER="test-admin",
    ADMIN_PASS="test-password",
)

import aiosmtplib
import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def smtp_calls(monkeypatch):
    """Replace the SMTP call everywhere, so no test can send real mail."""
    calls = []

    async def fake_send(message, **kwargs):
        calls.append({"message": message, **kwargs})

    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    return calls
