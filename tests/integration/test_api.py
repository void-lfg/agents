"""
Test FastAPI admin API endpoints.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
class TestAdminAPI:
    """Test admin API endpoints."""

    @pytest.fixture
    async def client(self):
        """Test client."""
        from void.admin.api.app import app
        from void.data.database import get_db

        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    async def test_health_check(self, client):
        """Test health check endpoint."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"

    async def test_list_accounts(self, client):
        """Test list accounts endpoint."""
        response = await client.get("/accounts")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_agents(self, client):
        """Test list agents endpoint."""
        response = await client.get("/agents")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_signals(self, client):
        """Test list signals endpoint."""
        response = await client.get("/signals")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_positions(self, client):
        """Test list positions endpoint."""
        response = await client.get("/positions")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint."""
        response = await client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
