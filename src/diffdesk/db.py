"""SQLite persistence for diffdesk."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from diffdesk.models import (
    DEFAULT_CHECKLIST,
    ChecklistStatus,
    DecisionRequest,
    FileStatus,
    FindingCreate,
    FindingSeverity,
    FindingStatus,
    FindingUpdate,
    ReviewCreate,
    ReviewSource,
    ReviewStatus,
    ReviewUpdate,
    RiskLevel,
    SettingsUpdate,
    TemplateItem,
)
from diffdesk.diff_parse import parse_unified_diff


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_db_path() -> Path:
    env = os.environ.get("DIFFDESK_DB")
    if env:
        return Path(env).expanduser().resolve()
    home = Path.home() / ".diffdesk"
    home.mkdir(parents=True, exist_ok=True)
    return home / "diffdesk.db"


class Database:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    status TEXT NOT NULL DEFAULT 'open',
                    risk TEXT NOT NULL DEFAULT 'med',
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'text',
                    patch TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    additions INTEGER NOT NULL DEFAULT 0,
                    deletions INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS checklist_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'todo',
                    notes TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
                    severity TEXT NOT NULL DEFAULT 'med',
                    file_path TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_files_review ON files(review_id);
                CREATE INDEX IF NOT EXISTS idx_checklist_review ON checklist_items(review_id);
                CREATE INDEX IF NOT EXISTS idx_findings_review ON findings(review_id);
                CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
                """
            )
            # Seed default template if missing
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", ("checklist_template",)
            ).fetchone()
            if row is None:
                template = [{"category": c, "label": l} for c, l in DEFAULT_CHECKLIST]
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?)",
                    ("checklist_template", json.dumps(template)),
                )

    # --- settings ---

    def get_checklist_template(self) -> list[dict[str, str]]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", ("checklist_template",)
            ).fetchone()
            if not row:
                return [{"category": c, "label": l} for c, l in DEFAULT_CHECKLIST]
            data = json.loads(row["value"])
            return data

    def update_checklist_template(self, items: list[TemplateItem] | list[dict]) -> list[dict]:
        payload = []
        for it in items:
            if isinstance(it, TemplateItem):
                payload.append({"category": it.category, "label": it.label})
            else:
                payload.append({"category": it["category"], "label": it["label"]})
        with self.session() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("checklist_template", json.dumps(payload)),
            )
        return payload

    # --- helpers ---

    def _review_counts(self, conn: sqlite3.Connection, review_id: int) -> dict[str, int]:
        file_count = conn.execute(
            "SELECT COUNT(*) AS c FROM files WHERE review_id = ?", (review_id,)
        ).fetchone()["c"]
        finding_count = conn.execute(
            "SELECT COUNT(*) AS c FROM findings WHERE review_id = ? AND status = 'open'",
            (review_id,),
        ).fetchone()["c"]
        cl = conn.execute(
            "SELECT "
            "SUM(CASE WHEN status != 'todo' THEN 1 ELSE 0 END) AS done, "
            "COUNT(*) AS total "
            "FROM checklist_items WHERE review_id = ?",
            (review_id,),
        ).fetchone()
        return {
            "file_count": file_count,
            "finding_count": finding_count,
            "checklist_done": cl["done"] or 0,
            "checklist_total": cl["total"] or 0,
        }

    def _row_to_review(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        counts = self._review_counts(conn, row["id"])
        return {
            "id": row["id"],
            "title": row["title"],
            "source": row["source"],
            "status": row["status"],
            "risk": row["risk"],
            "summary": row["summary"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            **counts,
        }

    # --- reviews ---

    def list_reviews(
        self,
        status: Optional[str] = None,
        risk: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if risk:
            clauses.append("risk = ?")
            params.append(risk)
        if q:
            clauses.append("(title LIKE ? OR summary LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM reviews {where} ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self.session() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_review(conn, r) for r in rows]

    def get_review(self, review_id: int) -> Optional[dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
            if not row:
                return None
            base = self._row_to_review(conn, row)
            files = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM files WHERE review_id = ? ORDER BY path", (review_id,)
                ).fetchall()
            ]
            checklist = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM checklist_items WHERE review_id = ? ORDER BY sort_order, id",
                    (review_id,),
                ).fetchall()
            ]
            findings = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM findings WHERE review_id = ? ORDER BY id DESC",
                    (review_id,),
                ).fetchall()
            ]
            base["files"] = files
            base["checklist"] = checklist
            base["findings"] = findings
            return base

    def create_review(self, data: ReviewCreate) -> dict[str, Any]:
        now = utcnow()
        with self.session() as conn:
            cur = conn.execute(
                """
                INSERT INTO reviews(title, source, status, risk, summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.title.strip(),
                    data.source.value if isinstance(data.source, ReviewSource) else data.source,
                    ReviewStatus.OPEN.value,
                    data.risk.value if isinstance(data.risk, RiskLevel) else data.risk,
                    data.summary or "",
                    now,
                    now,
                ),
            )
            review_id = int(cur.lastrowid)

            # files from diff
            parsed = parse_unified_diff(data.diff_text or "")
            for pf in parsed.files:
                conn.execute(
                    """
                    INSERT INTO files(review_id, path, language, patch, status, additions, deletions)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        pf.path,
                        pf.language,
                        pf.patch,
                        FileStatus.PENDING.value,
                        pf.additions,
                        pf.deletions,
                    ),
                )

            # checklist from template
            template = self._template_from_conn(conn)
            for idx, item in enumerate(template):
                conn.execute(
                    """
                    INSERT INTO checklist_items(review_id, category, label, status, notes, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        item["category"],
                        item["label"],
                        ChecklistStatus.TODO.value,
                        "",
                        idx,
                    ),
                )

        detail = self.get_review(review_id)
        assert detail is not None
        return detail

    def _template_from_conn(self, conn: sqlite3.Connection) -> list[dict[str, str]]:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", ("checklist_template",)
        ).fetchone()
        if not row:
            return [{"category": c, "label": l} for c, l in DEFAULT_CHECKLIST]
        return json.loads(row["value"])

    def update_review(self, review_id: int, data: ReviewUpdate) -> Optional[dict[str, Any]]:
        existing = self.get_review(review_id)
        if not existing:
            return None
        fields: list[str] = []
        params: list[Any] = []
        payload = data.model_dump(exclude_unset=True)
        for key in ("title", "source", "status", "risk", "summary"):
            if key in payload and payload[key] is not None:
                val = payload[key]
                if hasattr(val, "value"):
                    val = val.value
                fields.append(f"{key} = ?")
                params.append(val)
        if not fields:
            return existing
        fields.append("updated_at = ?")
        params.append(utcnow())
        params.append(review_id)
        with self.session() as conn:
            conn.execute(
                f"UPDATE reviews SET {', '.join(fields)} WHERE id = ?",
                params,
            )
        return self.get_review(review_id)

    def set_decision(self, review_id: int, decision: DecisionRequest | ReviewStatus | str) -> Optional[dict[str, Any]]:
        if isinstance(decision, DecisionRequest):
            status = decision.status
        elif isinstance(decision, ReviewStatus):
            status = decision
        else:
            status = ReviewStatus(decision)
        allowed = {
            ReviewStatus.SHIP,
            ReviewStatus.CHANGES_REQUESTED,
            ReviewStatus.ARCHIVED,
            ReviewStatus.IN_REVIEW,
            ReviewStatus.OPEN,
        }
        if status not in allowed:
            raise ValueError(f"Invalid decision status: {status}")
        return self.update_review(review_id, ReviewUpdate(status=status))

    def delete_review(self, review_id: int) -> bool:
        with self.session() as conn:
            cur = conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
            return cur.rowcount > 0

    # --- checklist ---

    def update_checklist_item(
        self, item_id: int, status: ChecklistStatus | str, notes: str | None = None
    ) -> Optional[dict[str, Any]]:
        st = status.value if isinstance(status, ChecklistStatus) else status
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM checklist_items WHERE id = ?", (item_id,)
            ).fetchone()
            if not row:
                return None
            if notes is None:
                conn.execute(
                    "UPDATE checklist_items SET status = ? WHERE id = ?",
                    (st, item_id),
                )
            else:
                conn.execute(
                    "UPDATE checklist_items SET status = ?, notes = ? WHERE id = ?",
                    (st, notes, item_id),
                )
            conn.execute(
                "UPDATE reviews SET updated_at = ? WHERE id = ?",
                (utcnow(), row["review_id"]),
            )
            updated = conn.execute(
                "SELECT * FROM checklist_items WHERE id = ?", (item_id,)
            ).fetchone()
            return dict(updated) if updated else None

    # --- findings ---

    def add_finding(self, review_id: int, data: FindingCreate) -> Optional[dict[str, Any]]:
        if not self.get_review(review_id):
            return None
        now = utcnow()
        with self.session() as conn:
            cur = conn.execute(
                """
                INSERT INTO findings(review_id, severity, file_path, title, body, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    data.severity.value if isinstance(data.severity, FindingSeverity) else data.severity,
                    data.file_path or "",
                    data.title.strip(),
                    data.body or "",
                    FindingStatus.OPEN.value,
                    now,
                ),
            )
            fid = int(cur.lastrowid)
            conn.execute(
                "UPDATE reviews SET updated_at = ? WHERE id = ?",
                (now, review_id),
            )
            row = conn.execute("SELECT * FROM findings WHERE id = ?", (fid,)).fetchone()
            return dict(row) if row else None

    def update_finding(self, finding_id: int, data: FindingUpdate) -> Optional[dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
            if not row:
                return None
            payload = data.model_dump(exclude_unset=True)
            fields: list[str] = []
            params: list[Any] = []
            for key in ("severity", "file_path", "title", "body", "status"):
                if key in payload and payload[key] is not None:
                    val = payload[key]
                    if hasattr(val, "value"):
                        val = val.value
                    fields.append(f"{key} = ?")
                    params.append(val)
            if not fields:
                return dict(row)
            params.append(finding_id)
            conn.execute(
                f"UPDATE findings SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.execute(
                "UPDATE reviews SET updated_at = ? WHERE id = ?",
                (utcnow(), row["review_id"]),
            )
            updated = conn.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
            return dict(updated) if updated else None

    def delete_finding(self, finding_id: int) -> bool:
        with self.session() as conn:
            row = conn.execute(
                "SELECT review_id FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM findings WHERE id = ?", (finding_id,))
            conn.execute(
                "UPDATE reviews SET updated_at = ? WHERE id = ?",
                (utcnow(), row["review_id"]),
            )
            return True

    def update_file_status(
        self, file_id: int, status: FileStatus | str
    ) -> Optional[dict[str, Any]]:
        st = status.value if isinstance(status, FileStatus) else status
        with self.session() as conn:
            row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
            if not row:
                return None
            conn.execute("UPDATE files SET status = ? WHERE id = ?", (st, file_id))
            conn.execute(
                "UPDATE reviews SET updated_at = ? WHERE id = ?",
                (utcnow(), row["review_id"]),
            )
            updated = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
            return dict(updated) if updated else None

    # --- dashboard ---

    def dashboard(self) -> dict[str, Any]:
        with self.session() as conn:
            def count(status: str | None = None, risk: str | None = None) -> int:
                clauses = []
                params: list[Any] = []
                if status:
                    clauses.append("status = ?")
                    params.append(status)
                if risk:
                    clauses.append("risk = ?")
                    params.append(risk)
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                return conn.execute(f"SELECT COUNT(*) AS c FROM reviews {where}", params).fetchone()[
                    "c"
                ]

            rows = conn.execute(
                "SELECT * FROM reviews ORDER BY updated_at DESC LIMIT 8"
            ).fetchall()
            recent = [self._row_to_review(conn, r) for r in rows]
            return {
                "open_count": count("open"),
                "in_review_count": count("in_review"),
                "high_risk_count": count(risk="high"),
                "ship_count": count("ship"),
                "changes_requested_count": count("changes_requested"),
                "total_count": count(),
                "recent": recent,
            }

    # --- seed ---

    def seed_demo(self, force: bool = False) -> dict[str, Any]:
        """Insert demo reviews if empty (or always when force)."""
        with self.session() as conn:
            n = conn.execute("SELECT COUNT(*) AS c FROM reviews").fetchone()["c"]
        if n > 0 and not force:
            return {"seeded": False, "reason": "already has data", "count": n}

        samples = [
            ReviewCreate(
                title="Agent: add rate limiter to API",
                source=ReviewSource.AGENT,
                risk=RiskLevel.HIGH,
                summary="Cursor agent added a token-bucket middleware. Needs security + edge-case pass.",
                diff_text=_SAMPLE_DIFF_RATE_LIMIT,
            ),
            ReviewCreate(
                title="PR #142: refactor auth helpers",
                source=ReviewSource.PR,
                risk=RiskLevel.MED,
                summary="Human PR with AI-assisted rename. Check scope creep.",
                diff_text=_SAMPLE_DIFF_AUTH,
            ),
            ReviewCreate(
                title="Manual: fix empty-state copy",
                source=ReviewSource.MANUAL,
                risk=RiskLevel.LOW,
                summary="Tiny UI string change from ChatGPT suggestion.",
                diff_text=_SAMPLE_DIFF_COPY,
            ),
        ]
        created = []
        for s in samples:
            created.append(self.create_review(s))

        # Mark one as in_review with a finding
        if created:
            rid = created[0]["id"]
            self.set_decision(rid, ReviewStatus.IN_REVIEW)
            self.add_finding(
                rid,
                FindingCreate(
                    severity=FindingSeverity.HIGH,
                    file_path="app/middleware/rate_limit.py",
                    title="Hard-coded Redis URL with password",
                    body="Looks like a secret snuck into the patch. Move to env var and rotate.",
                ),
            )
            # mark a checklist item
            detail = self.get_review(rid)
            if detail and detail["checklist"]:
                self.update_checklist_item(detail["checklist"][0]["id"], ChecklistStatus.PASS)
                self.update_checklist_item(
                    detail["checklist"][5]["id"],
                    ChecklistStatus.FAIL,
                    notes="Secret in patch",
                )

        return {"seeded": True, "count": len(created), "ids": [c["id"] for c in created]}


_SAMPLE_DIFF_RATE_LIMIT = """\
diff --git a/app/middleware/rate_limit.py b/app/middleware/rate_limit.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/app/middleware/rate_limit.py
@@ -0,0 +1,28 @@
+import time
+from collections import defaultdict
+
+REDIS_URL = "redis://:supersecret@localhost:6379/0"
+
+class RateLimiter:
+    def __init__(self, limit=100, window=60):
+        self.limit = limit
+        self.window = window
+        self.hits = defaultdict(list)
+
+    def allow(self, key: str) -> bool:
+        now = time.time()
+        bucket = self.hits[key]
+        self.hits[key] = [t for t in bucket if now - t < self.window]
+        if len(self.hits[key]) >= self.limit:
+            return False
+        self.hits[key].append(now)
+        return True
+
+def get_limiter():
+    return RateLimiter()
diff --git a/app/main.py b/app/main.py
index 2222222..3333333 100644
--- a/app/main.py
+++ b/app/main.py
@@ -1,5 +1,8 @@
 from fastapi import FastAPI
+from app.middleware.rate_limit import get_limiter
 
 app = FastAPI()
+limiter = get_limiter()
 
 @app.get("/health")
 def health():
@@ -7,3 +10,9 @@ def health():
 
 @app.get("/items")
 def items():
+    if not limiter.allow("global"):
+        return {"error": "rate limited"}
     return []
"""

_SAMPLE_DIFF_AUTH = """\
diff --git a/lib/auth.py b/lib/auth.py
index aaaaaaa..bbbbbbb 100644
--- a/lib/auth.py
+++ b/lib/auth.py
@@ -10,12 +10,14 @@ def verify_token(token: str) -> dict:
     if not token:
         raise ValueError("missing token")
-    payload = decode(token, SECRET)
+    payload = decode(token, SECRET, algorithms=["HS256"])
     if payload.get("exp", 0) < time.time():
         raise ValueError("expired")
     return payload
 
+def require_admin(user: dict) -> None:
+    if user.get("role") != "admin":
+        raise PermissionError("admin only")
+
 def current_user(headers: dict) -> dict:
     auth = headers.get("authorization", "")
     token = auth.removeprefix("Bearer ").strip()
"""

_SAMPLE_DIFF_COPY = """\
diff --git a/web/empty.html b/web/empty.html
index ccccccc..ddddddd 100644
--- a/web/empty.html
+++ b/web/empty.html
@@ -4,7 +4,7 @@
   <div class="empty">
-    <h2>No data</h2>
-    <p>Nothing here yet.</p>
+    <h2>No reviews yet</h2>
+    <p>Paste an agent diff to start your first structured review.</p>
   </div>
"""
