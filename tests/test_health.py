"""Basic health and system endpoints test."""

import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import create_app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify that GET /health returns HTTP 200 with ok status and environment."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "app_env" in data
        assert "version" in data
        assert "X-Request-ID" in response.headers
