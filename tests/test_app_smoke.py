def test_root_login_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Quickfire Math" in r.text


def test_dashboard_redirects_without_login(client):
    r = client.get("/dashboard", allow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert r.headers.get("location") == "/"

