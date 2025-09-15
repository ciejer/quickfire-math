import json
from fastapi.testclient import TestClient


def _finish_payload(drill_type: str, items=20, correct=20, elapsed_ms=30000):
    # Build a simple qlog where first attempts are correct up to `correct`
    qlog = []
    for i in range(items):
        ok = i < correct
        qlog.append({
            "prompt": f"{i+1} + {i+1}",
            "a": i+1,
            "b": i+1,
            "correct_answer": (i+1)+(i+1),
            "given_answer": (i+1)+(i+1) if ok else 0,
            "correct": ok,
            "started_at": "2024-01-01T00:00:00",
            "elapsed_ms": 100,
        })
    return {
        "drill_type": drill_type,
        "elapsed_ms": str(elapsed_ms),
        "settings_human": "Level 1",
        "question_count": str(items),
        "score": str(correct),
        "qlog": json.dumps(qlog),
    }


def test_start_next_and_finish_star_and_progress(test_client: TestClient):
    uid = __import__("tests.conftest", fromlist=["create_user"]).create_user(test_client, "Dora")

    # Start a drill (addition)
    r = test_client.post("/start", data={"drill_type": "addition"})
    assert r.status_code == 200
    assert "equation" in r.text

    # Next question JSON
    r = test_client.post("/next", data={"drill_type": "addition"})
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"prompt", "answer", "tts"}

    # Finish with a star-worthy run
    pay = test_client.post("/finish", data=_finish_payload("addition", items=20, correct=19, elapsed_ms=20000)).json()
    assert pay["ok"] is True
    assert pay["star"] is True
    assert "need_hint" in pay

    # Progress reflects the new star in last5
    r = test_client.get("/progress")
    prog = r.json()
    assert "addition" in prog
    assert prog["addition"]["last5"].endswith("1")


def test_finish_no_star_and_feedback(test_client: TestClient):
    uid = __import__("tests.conftest", fromlist=["create_user"]).create_user(test_client, "Eli")
    # Too slow to pass time gate
    pay = test_client.post("/finish", data=_finish_payload("addition", items=20, correct=20, elapsed_ms=999999)).json()
    assert pay["ok"] is True
    assert pay["star"] is False
    assert isinstance(pay.get("fail_msg"), str) and len(pay["fail_msg"]) > 0
    # Progress updated last5 with a 0
    prog = test_client.get("/progress").json()
    assert prog["addition"]["last5"].endswith("0")


def test_level_up_after_three_stars(test_client: TestClient):
    __import__("tests.conftest", fromlist=["create_user"]).create_user(test_client, "Finn")
    # Earn three stars in a row
    for i in range(3):
        pay = test_client.post("/finish", data=_finish_payload("multiplication", items=20, correct=19, elapsed_ms=25000)).json()
    assert pay["star"] is True
    assert pay["level_up"] is True
    assert isinstance(pay["new_level"], int) and pay["new_level"] >= 2
    # After level up, progress last5 resets
    prog = test_client.get("/progress").json()
    assert prog["multiplication"]["last5"] == ""


def test_feed_and_stats_endpoints(test_client: TestClient):
    __import__("tests.conftest", fromlist=["create_user"]).create_user(test_client, "Gail")
    # Submit two drills
    test_client.post("/finish", data=_finish_payload("subtraction", items=20, correct=18, elapsed_ms=18000))
    test_client.post("/finish", data=_finish_payload("division", items=20, correct=17, elapsed_ms=22000))
    # Feed
    feed = test_client.get("/feed").json()
    assert isinstance(feed.get("items"), list) and len(feed["items"]) >= 2
    # Stats
    stats = test_client.get("/stats", params={"tz_offset": 0}).json()
    assert {"total", "addition", "subtraction", "multiplication", "division"}.issubset(stats.keys())


def test_reports_endpoints(test_client: TestClient):
    __import__("tests.conftest", fromlist=["create_user"]).create_user(test_client, "Hana")
    # Create a multiplication session with some wrong answers
    pay = test_client.post("/finish", data=_finish_payload("multiplication", items=20, correct=15, elapsed_ms=30000))
    # Endpoints
    m = test_client.get("/report/multiplication").json()
    a = test_client.get("/report/addition").json()
    s = test_client.get("/report/subtraction").json()
    assert m["labels_from"] == 1 and m["labels_to"] == 12 and isinstance(m["grid"], dict)
    assert a["labels_from"] == 0 and isinstance(a["grid"], dict)
    assert s["labels_from"] == 0 and isinstance(s["grid"], dict)

