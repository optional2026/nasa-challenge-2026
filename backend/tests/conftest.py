import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
_tmp = tempfile.mkdtemp(prefix="astra-test-")
os.environ["ASTRA_DATA_DIR"] = _tmp
os.environ["ASTRA_DB_PATH"] = str(Path(_tmp) / "test.sqlite3")
os.environ["ASTRA_SECRET_KEY"] = "test-secret-key-for-unit-tests-only-0123456789"
os.environ["ASTRA_DISABLE_SYNC_WORKER"] = "1"
os.environ["ASTRA_FRONTEND_DIST"] = str(Path(_tmp) / "no-dist")

from starlette.testclient import TestClient  # noqa: E402

from astra.app import app  # noqa: E402

PASSWORD = "astra-demo"            # Earth-side demo accounts (admin, ramirez)
CREW_PASSWORD = "optionalwillwin"  # shared demo password of the three pre-created crew accounts
CREW_USERS = ("vega", "okafor", "mori")


def password_for(username):
    return CREW_PASSWORD if username in CREW_USERS else PASSWORD


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, username):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password_for(username)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def auth(client):
    cache = {}

    def get(username):
        if username not in cache:
            cache[username] = _login(client, username)
        return cache[username]
    return get


@pytest.fixture(scope="session")
def device_keys(client):
    import json
    from astra.seed import device_keys_path
    return json.loads(device_keys_path().read_text())
