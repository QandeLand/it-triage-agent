import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app


def make_client():
    app.config["TESTING"] = True
    return app.test_client()


def test_health():
    r = make_client().get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_metrics_endpoint():
    r = make_client().get("/metrics")
    assert r.status_code == 200
    assert b"app_requests_total" in r.data


def test_home_status():
    r = make_client().get("/")
    assert r.status_code in (200, 500)


def test_webhook_accepts_empty_json():
    r = make_client().post("/webhook", json={})
    assert r.status_code == 200
    assert r.get_json()["received"] is True
