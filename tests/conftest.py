import os
import sys
import tempfile
import pathlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def test_client(monkeypatch):
    # Ensure repository root is importable as a package ('app' module)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    # Use a stable DB file under tests/data for Windows reliability
    data_dir = pathlib.Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "test.sqlite"
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass
    monkeypatch.setenv("APP_DB_PATH", str(db_path))

    # Import after setting env so storage binds to this DB
    from app.main import create_app
    app = create_app()
    with TestClient(app) as client:
        yield client
    # Dispose DB engine and clean up file
    try:
        from app.storage import engine
        engine.dispose()
    except Exception:
        pass
    try:
        if db_path.exists():
            db_path.unlink()
    except Exception:
        pass


def create_user(client: TestClient, name: str = "Alice") -> int:
    r = client.post("/user/add", data={"display_name": name}, allow_redirects=False)
    assert r.status_code in (303, 307)
    # Cookie uid is set on redirect
    uid_cookie = r.cookies.get("uid")
    assert uid_cookie is not None
    return int(uid_cookie)


# Backward-compatible fixture name some tests expect
@pytest.fixture(name="client")
def _client_fixture(test_client: TestClient):
    return test_client
