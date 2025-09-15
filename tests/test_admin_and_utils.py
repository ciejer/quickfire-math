from fastapi.testclient import TestClient


def test_admin_login_and_delete_user(test_client: TestClient):
    # Create two users
    create_user = __import__("tests.conftest", fromlist=["create_user"]).create_user
    uid1 = create_user(test_client, "Ivy")
    uid2 = create_user(test_client, "Jake")

    # Get current admin password from DB (startup ensured it exists)
    from app.storage import get_session
    from app.models import AdminConfig, User
    with get_session() as s:
        pwd = s.exec(__import__('sqlmodel').select(AdminConfig)).first().admin_password_plain
        assert pwd
        assert s.get(User, uid2) is not None

    # Login as admin
    r = test_client.post("/admin/login", data={"password": pwd}, allow_redirects=False)
    assert r.status_code in (303, 307)
    # Admin cookie should be set
    assert r.cookies.get("is_admin") == "1"

    # Delete user 2
    r = test_client.post("/admin/delete_user", data={"user_id": uid2})
    assert r.status_code in (200, 303, 307)
    with get_session() as s:
        assert s.get(User, uid2) is None


def test_logic_utils():
    from app.logic import compute_first_try_metrics, star_decision, levelup_decision, is_commutative_op_key
    # Metrics: 3 prompts, one missed on first try
    qlog = [
        {"prompt":"2 + 2","correct":True,"started_at":"t1"},
        {"prompt":"3 + 2","correct":False,"started_at":"t2"},
        {"prompt":"3 + 2","correct":True,"started_at":"t3"},
        {"prompt":"4 + 2","correct":True,"started_at":"t4"},
    ]
    m = compute_first_try_metrics(qlog)
    assert m["items"] == 3 and m["first_try_correct"] == 2 and 0 < m["acc"] < 1

    # Star decision: meets both accuracy and time
    ok, exp = star_decision({"items":20, "acc":0.95, "first_try_correct":19}, total_time_ms=10000, target_time_sec=30)
    assert ok is True
    # Too slow
    ok, exp = star_decision({"items":20, "acc":0.95, "first_try_correct":19}, total_time_ms=120000, target_time_sec=30)
    assert ok is False and exp["why"] == "too_slow"
    # Accuracy too low
    ok, exp = star_decision({"items":20, "acc":0.5, "first_try_correct":10}, total_time_ms=10000, target_time_sec=30)
    assert ok is False and exp["why"] == "accuracy_below_gate"

    # Level-up rule
    assert levelup_decision("", True) is False
    assert levelup_decision("11", True) is True  # becomes 111 -> 3 of 5, and 2 of last 3

    # Commutative key helper
    k1 = is_commutative_op_key("4 × 6")
    k2 = is_commutative_op_key("6 × 4")
    assert k1 == k2


def test_next_problem_duplicate_avoidance(test_client: TestClient):
    __import__("tests.conftest", fromlist=["create_user"]).create_user(test_client, "Kate")
    # Request a next with avoid prompt; ensure it tries to avoid exact repeat
    avoid = "4 × 6"
    r = test_client.post("/next", data={"drill_type":"multiplication", "avoid_prompt": avoid})
    assert r.status_code == 200
    data = r.json()
    assert data["prompt"] != avoid
