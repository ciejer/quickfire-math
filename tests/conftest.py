import os
from pathlib import Path
import pytest


@pytest.fixture(scope="session")
def test_db_path() -> str:
    # Use a workspace-local SQLite file to avoid writing to /data
    p = Path(__file__).parent / "data" / "test.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


@pytest.fixture(scope="session")
def client(test_db_path):
    # Ensure the app uses the test database before importing app modules
    os.environ["APP_DB_PATH"] = test_db_path
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c

