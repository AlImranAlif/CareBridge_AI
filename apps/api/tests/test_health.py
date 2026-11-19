from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_live_endpoint_and_application_startup() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-request-id" in response.headers


def test_ready_without_database_configuration() -> None:
    app.dependency_overrides.clear()
    app.dependency_overrides[__import__("app.core.config", fromlist=["get_settings"]).get_settings] = lambda: Settings(database_url=None)
    try:
        response = TestClient(app).get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert "replace-me" not in response.text


def test_ready_checks_database_connectivity() -> None:
    from app.core.config import get_settings

    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: Settings(database_url="postgresql+psycopg://user:secret@localhost/db")
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    with patch("app.api.v1.health.get_database_engine", return_value=engine):
        try:
            response = TestClient(app).get("/api/v1/health/ready")
        finally:
            app.dependency_overrides.clear()
    assert response.status_code == 200
    connection.execute.assert_called_once()


def test_ready_database_failure_is_generic_and_does_not_log_credentials(caplog) -> None:
    from app.core.config import get_settings

    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: Settings(database_url="postgresql+psycopg://user:secret@localhost/db")
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError("connection failed: secret")
    with patch("app.api.v1.health.get_database_engine", return_value=engine):
        try:
            response = TestClient(app).get("/api/v1/health/ready")
        finally:
            app.dependency_overrides.clear()
    assert response.status_code == 503
    assert "secret" not in response.text
    assert "secret" not in caplog.text
