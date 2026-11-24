"""Pytest test configuration and fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import create_app


@pytest.fixture
def app():
    """Create test application instance."""
    return create_app()


@pytest.fixture
async def async_client(app):
    """Provide asynchronous HTTP client for API tests."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
