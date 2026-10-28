from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import create_app


def test_liveness_does_not_require_mysql():
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_mysql_failure_returns_503_without_connection_details():
    class UnavailableDatabase:
        def execute(self, _statement):
            raise OperationalError("SELECT 1", {}, Exception("private-connection-information"))

    app = create_app()
    app.dependency_overrides[get_db] = lambda: UnavailableDatabase()
    with TestClient(app) as client:
        response = client.get("/api/health/db")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "mysql"}
    assert "private-connection-information" not in response.text
