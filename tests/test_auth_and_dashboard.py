from fastapi.testclient import TestClient


def test_login_page_and_add_user(test_client: TestClient):
    # GET / shows login page
    r = test_client.get("/")
    assert r.status_code == 200
    # Be flexible with text due to font/encoding: look for admin link or user-add form
    assert ("/admin" in r.text) and ("/user/add" in r.text)

    # Add a new user and get redirected with uid cookie
    uid = __import__("tests.conftest", fromlist=["create_user"]).create_user(test_client, "Bob")
    assert isinstance(uid, int) and uid > 0


def test_dashboard_requires_login_and_renders(test_client: TestClient):
    # Without cookie it should redirect
    r = test_client.get("/dashboard", allow_redirects=False)
    assert r.status_code in (302, 303, 307)

    uid = __import__("tests.conftest", fromlist=["create_user"]).create_user(test_client, "Cara")
    # Now dashboard should render
    r = test_client.get("/dashboard")
    assert r.status_code == 200
    assert "Choose a drill" in r.text
