import os
import tempfile
import uuid

_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "STORAGE_DIR": _tmp,
    "APP_ENV_FILE": f"{_tmp}/test.env",
    "SECRET_KEY": "test-secret-test-secret-test-secret-123",
    "ADMIN_PASSWORD": "adminpass123",
    "SEPAY_API_KEY": "sepay-key",
    "CASSO_SECURE_TOKEN": "casso-token",
    "CELERY_ALWAYS_EAGER": "1",
    "REGISTER_PER_HOUR": "100000",
    "APP_ENV": "dev",
    "ALLOW_PRIVATE_MODEL_URLS": "1",
    "FAST_RENDER_COST": "1",
    "HEAVY_RENDER_COST": "10",
    "VILAO_BASE_URL": "",
    "VILAO_API_KEY": "",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _auth(client, username, password="password123", email=None):
    phone = "09" + str(10000000 + (uuid.uuid4().int % 89999999))
    r = client.post("/api/auth/register", json={"username": username, "email": email or f"{username}@x.io",
                                                "password": password, "phone": phone})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]["id"]


@pytest.fixture()
def make_user(client):
    def f():
        return _auth(client, f"user{uuid.uuid4().hex[:12]}")
    return f


@pytest.fixture(scope="session")
def admin_headers(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}
