from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.config import settings


def test_health_check_live(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert data["database_reachable"] is True
    assert isinstance(data["api_key_configured"], bool)
    assert "models" in data
    assert data["models"]["llm"] == "qwen3.5:4b"
    assert data["models"]["embedding"] == "nomic-embed-text"

    # Ollama is running locally with both models pulled
    assert data["ollama_reachable"] is True
    assert data["models"]["llm_installed"] is True
    assert data["models"]["embedding_installed"] is True
    assert data["models"]["installed"] is True
    assert data["status"] == "healthy"


def test_health_check_api_v1(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["database_reachable"] is True
    assert data["status"] == "healthy"


def test_health_check_when_ollama_unreachable(client: TestClient) -> None:
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["database_reachable"] is True
        assert data["ollama_reachable"] is False
        assert data["models"]["installed"] is False
        assert data["status"] == "degraded"


def test_api_key_configured_never_leaks_key(client: TestClient) -> None:
    # Temporarily set fake api key
    original_key = settings.youtube_api_key
    try:
        settings.youtube_api_key = "AIzaSySecretFakeApiKey12345"
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["api_key_configured"] is True

        # Assert secret never appears anywhere in the response text
        assert "AIzaSySecretFakeApiKey12345" not in response.text
        assert "12345" not in response.text
    finally:
        settings.youtube_api_key = original_key
