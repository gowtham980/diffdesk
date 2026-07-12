"""API tests for reviews, decisions, checklist."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from diffdesk.app import create_app
from diffdesk.db import Database


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DIFFDESK_DB", str(db_path))
    db = Database(db_path)
    app = create_app(db)
    with TestClient(app) as c:
        yield c


DIFF = """\
diff --git a/hello.py b/hello.py
new file mode 100644
index 000..111
--- /dev/null
+++ b/hello.py
@@ -0,0 +1,2 @@
+def hi():
+    return 1
"""


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["name"] == "diffdesk"


def test_create_list_get_review(client: TestClient):
    r = client.post(
        "/api/reviews",
        json={
            "title": "Agent change",
            "source": "agent",
            "risk": "high",
            "summary": "demo",
            "diff_text": DIFF,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Agent change"
    assert body["status"] == "open"
    assert body["file_count"] == 1
    assert body["checklist_total"] >= 8
    assert len(body["files"]) == 1
    assert body["files"][0]["path"] == "hello.py"
    rid = body["id"]

    listed = client.get("/api/reviews")
    assert listed.status_code == 200
    assert any(x["id"] == rid for x in listed.json())

    got = client.get(f"/api/reviews/{rid}")
    assert got.status_code == 200
    assert got.json()["id"] == rid


def test_decision_transition(client: TestClient):
    r = client.post(
        "/api/reviews",
        json={"title": "Decide me", "source": "manual", "diff_text": ""},
    )
    rid = r.json()["id"]

    for status in ("in_review", "ship", "changes_requested", "archived"):
        d = client.post(f"/api/reviews/{rid}/decision", json={"status": status})
        assert d.status_code == 200, d.text
        assert d.json()["status"] == status


def test_dashboard_and_seed(client: TestClient):
    s = client.post("/api/seed")
    assert s.status_code == 200
    assert s.json()["seeded"] is True

    dash = client.get("/api/dashboard")
    assert dash.status_code == 200
    data = dash.json()
    assert data["total_count"] >= 3
    assert len(data["recent"]) >= 1


def test_finding_and_checklist(client: TestClient):
    r = client.post(
        "/api/reviews",
        json={"title": "Findings", "source": "agent", "diff_text": DIFF},
    )
    body = r.json()
    rid = body["id"]
    item_id = body["checklist"][0]["id"]

    u = client.patch(
        f"/api/checklist/{item_id}",
        json={"status": "pass", "notes": "looks good"},
    )
    assert u.status_code == 200
    assert u.json()["status"] == "pass"

    f = client.post(
        f"/api/reviews/{rid}/findings",
        json={
            "title": "Possible secret",
            "severity": "high",
            "file_path": "hello.py",
            "body": "check env usage",
        },
    )
    assert f.status_code == 201
    fid = f.json()["id"]

    up = client.patch(f"/api/findings/{fid}", json={"status": "resolved"})
    assert up.status_code == 200
    assert up.json()["status"] == "resolved"


def test_html_pages(client: TestClient):
    assert client.get("/").status_code == 200
    assert client.get("/reviews").status_code == 200
    assert client.get("/reviews/new").status_code == 200
    assert client.get("/settings").status_code == 200
    assert client.get("/static/css/app.css").status_code == 200

    r = client.post(
        "/api/reviews",
        json={"title": "UI", "source": "pr", "diff_text": DIFF},
    )
    rid = r.json()["id"]
    page = client.get(f"/reviews/{rid}")
    assert page.status_code == 200
    assert b"AI checklist" in page.content
    assert b"hello.py" in page.content


def test_filter_reviews(client: TestClient):
    client.post(
        "/api/reviews",
        json={"title": "Alpha high", "risk": "high", "source": "agent"},
    )
    client.post(
        "/api/reviews",
        json={"title": "Beta low", "risk": "low", "source": "manual"},
    )
    high = client.get("/api/reviews", params={"risk": "high"})
    assert all(x["risk"] == "high" for x in high.json())
    q = client.get("/api/reviews", params={"q": "Alpha"})
    assert len(q.json()) >= 1
    assert "Alpha" in q.json()[0]["title"]


def test_not_found(client: TestClient):
    assert client.get("/api/reviews/99999").status_code == 404
