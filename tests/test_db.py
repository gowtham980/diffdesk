"""Database unit tests."""

from pathlib import Path

from diffdesk.db import Database
from diffdesk.models import (
    FindingCreate,
    FindingSeverity,
    ReviewCreate,
    ReviewSource,
    ReviewStatus,
    RiskLevel,
)


def test_create_and_decision(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    review = db.create_review(
        ReviewCreate(
            title="T",
            source=ReviewSource.AGENT,
            risk=RiskLevel.MED,
            summary="s",
            diff_text="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+x\n",
        )
    )
    assert review["id"] >= 1
    assert review["file_count"] == 1
    updated = db.set_decision(review["id"], ReviewStatus.SHIP)
    assert updated["status"] == "ship"


def test_template_and_seed(tmp_path: Path):
    db = Database(tmp_path / "t2.db")
    tpl = db.get_checklist_template()
    assert len(tpl) >= 8
    result = db.seed_demo()
    assert result["seeded"] is True
    again = db.seed_demo()
    assert again["seeded"] is False
    forced = db.seed_demo(force=True)
    assert forced["seeded"] is True


def test_findings(tmp_path: Path):
    db = Database(tmp_path / "t3.db")
    r = db.create_review(ReviewCreate(title="F", source=ReviewSource.MANUAL))
    f = db.add_finding(
        r["id"],
        FindingCreate(
            title="bug",
            severity=FindingSeverity.LOW,
            body="details",
        ),
    )
    assert f is not None
    assert f["title"] == "bug"
