import os
import tempfile

import pytest

# Point the app at a throwaway SQLite file before importing it, so tests
# never touch the real data/state/app.sqlite.
_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".sqlite")
os.close(_tmp_db_fd)
os.environ["DB_PATH_OVERRIDE"] = _tmp_db_path
os.environ['BACKGROUND_JOBS_ENABLED'] = 'false'

from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """Registers a throwaway user and returns an Authorization header dict."""
    email = f"test_{os.urandom(4).hex()}@example.com"
    resp = client.post("/api/auth/register", json={"email": email, "password": "testpass123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}
