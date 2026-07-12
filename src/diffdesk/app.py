"""FastAPI application — HTML UI + JSON API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from diffdesk import __version__
from diffdesk.db import Database
from diffdesk.diff_parse import render_diff_html_lines
from diffdesk.models import (
    ChecklistUpdate,
    DecisionRequest,
    FileStatus,
    FindingCreate,
    FindingUpdate,
    ReviewCreate,
    ReviewSource,
    ReviewStatus,
    ReviewUpdate,
    RiskLevel,
    SettingsUpdate,
    TemplateItem,
)

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def get_db() -> Database:
    return Database()


def create_app(db: Database | None = None) -> FastAPI:
    database = db or Database()
    app = FastAPI(
        title="diffdesk",
        description="Local-first AI code review workspace",
        version=__version__,
    )
    app.state.db = database

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals["app_version"] = __version__
    templates.env.filters["diff_lines"] = lambda p: render_diff_html_lines(p or "")

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # -------- helpers --------

    def flash_redirect(url: str, error: str | None = None) -> RedirectResponse:
        # simple query flash
        if error:
            sep = "&" if "?" in url else "?"
            return RedirectResponse(f"{url}{sep}error={error}", status_code=303)
        return RedirectResponse(url, status_code=303)

    # ==================== HTML pages ====================

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        stats = database.dashboard()
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "active": "dashboard",
                "stats": stats,
                "page_title": "Dashboard",
            },
        )

    @app.get("/reviews", response_class=HTMLResponse)
    async def reviews_list(
        request: Request,
        status: Optional[str] = None,
        risk: Optional[str] = None,
        q: Optional[str] = None,
    ):
        reviews = database.list_reviews(status=status, risk=risk, q=q)
        return templates.TemplateResponse(
            request,
            "reviews.html",
            {
                "active": "reviews",
                "reviews": reviews,
                "filter_status": status or "",
                "filter_risk": risk or "",
                "filter_q": q or "",
                "page_title": "Reviews",
                "statuses": [s.value for s in ReviewStatus],
                "risks": [r.value for r in RiskLevel],
            },
        )

    @app.get("/reviews/new", response_class=HTMLResponse)
    async def reviews_new(request: Request):
        return templates.TemplateResponse(
            request,
            "review_new.html",
            {
                "active": "new",
                "page_title": "New Review",
                "sources": [s.value for s in ReviewSource],
                "risks": [r.value for r in RiskLevel],
            },
        )

    @app.post("/reviews/new", response_class=HTMLResponse)
    async def reviews_create_form(
        request: Request,
        title: str = Form(...),
        source: str = Form("manual"),
        risk: str = Form("med"),
        summary: str = Form(""),
        diff_text: str = Form(""),
    ):
        title = (title or "").strip()
        if not title:
            return templates.TemplateResponse(
                request,
                "review_new.html",
                {
                    "active": "new",
                    "page_title": "New Review",
                    "sources": [s.value for s in ReviewSource],
                    "risks": [r.value for r in RiskLevel],
                    "error": "Title is required.",
                    "form": {
                        "title": title,
                        "source": source,
                        "risk": risk,
                        "summary": summary,
                        "diff_text": diff_text,
                    },
                },
                status_code=400,
            )
        try:
            review = database.create_review(
                ReviewCreate(
                    title=title,
                    source=ReviewSource(source),
                    risk=RiskLevel(risk),
                    summary=summary,
                    diff_text=diff_text,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return templates.TemplateResponse(
                request,
                "review_new.html",
                {
                    "active": "new",
                    "page_title": "New Review",
                    "sources": [s.value for s in ReviewSource],
                    "risks": [r.value for r in RiskLevel],
                    "error": str(exc),
                    "form": {
                        "title": title,
                        "source": source,
                        "risk": risk,
                        "summary": summary,
                        "diff_text": diff_text,
                    },
                },
                status_code=400,
            )
        return RedirectResponse(f"/reviews/{review['id']}", status_code=303)

    @app.get("/reviews/{review_id}", response_class=HTMLResponse)
    async def review_detail(request: Request, review_id: int, file: Optional[int] = None):
        review = database.get_review(review_id)
        if not review:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "active": "reviews",
                    "page_title": "Not found",
                    "error_code": 404,
                    "error_message": f"Review #{review_id} was not found.",
                },
                status_code=404,
            )
        selected = None
        if review["files"]:
            if file is not None:
                selected = next((f for f in review["files"] if f["id"] == file), None)
            if selected is None:
                selected = review["files"][0]
        return templates.TemplateResponse(
            request,
            "review_detail.html",
            {
                "active": "reviews",
                "page_title": review["title"],
                "review": review,
                "selected_file": selected,
                "diff_lines": render_diff_html_lines(selected["patch"]) if selected else [],
            },
        )

    @app.post("/reviews/{review_id}/decision")
    async def review_decision_form(review_id: int, status: str = Form(...)):
        review = database.get_review(review_id)
        if not review:
            raise HTTPException(404, "Review not found")
        try:
            database.set_decision(review_id, ReviewStatus(status))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse(f"/reviews/{review_id}", status_code=303)

    @app.post("/reviews/{review_id}/checklist/{item_id}")
    async def checklist_form(
        review_id: int,
        item_id: int,
        status: str = Form(...),
        notes: str = Form(""),
    ):
        item = database.update_checklist_item(item_id, status, notes)
        if not item:
            raise HTTPException(404, "Checklist item not found")
        return RedirectResponse(f"/reviews/{review_id}#checklist", status_code=303)

    @app.post("/reviews/{review_id}/findings")
    async def finding_form(
        review_id: int,
        title: str = Form(...),
        severity: str = Form("med"),
        file_path: str = Form(""),
        body: str = Form(""),
    ):
        if not title.strip():
            return RedirectResponse(f"/reviews/{review_id}?error=Finding+title+required", status_code=303)
        finding = database.add_finding(
            review_id,
            FindingCreate(
                title=title.strip(),
                severity=severity,  # type: ignore[arg-type]
                file_path=file_path,
                body=body,
            ),
        )
        if not finding:
            raise HTTPException(404, "Review not found")
        return RedirectResponse(f"/reviews/{review_id}#findings", status_code=303)

    @app.post("/reviews/{review_id}/findings/{finding_id}/status")
    async def finding_status_form(review_id: int, finding_id: int, status: str = Form(...)):
        updated = database.update_finding(finding_id, FindingUpdate(status=status))  # type: ignore[arg-type]
        if not updated:
            raise HTTPException(404, "Finding not found")
        return RedirectResponse(f"/reviews/{review_id}#findings", status_code=303)

    @app.post("/files/{file_id}/status")
    async def file_status_form(file_id: int, status: str = Form(...), review_id: int = Form(...)):
        updated = database.update_file_status(file_id, FileStatus(status))
        if not updated:
            raise HTTPException(404, "File not found")
        return RedirectResponse(f"/reviews/{review_id}?file={file_id}", status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        template = database.get_checklist_template()
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "active": "settings",
                "page_title": "Settings",
                "template": template,
                "db_path": str(database.path),
            },
        )

    @app.post("/settings/checklist")
    async def settings_checklist_form(request: Request):
        form = await request.form()
        categories = form.getlist("category")
        labels = form.getlist("label")
        items = []
        for c, l in zip(categories, labels):
            c, l = str(c).strip(), str(l).strip()
            if c and l:
                items.append(TemplateItem(category=c, label=l))
        if not items:
            return RedirectResponse("/settings?error=Need+at+least+one+item", status_code=303)
        database.update_checklist_template(items)
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/seed")
    async def seed_form(force: str = Form("0")):
        database.seed_demo(force=force in {"1", "true", "yes", "on"})
        return RedirectResponse("/?seeded=1", status_code=303)

    # ==================== JSON API ====================

    @app.get("/api/health")
    async def api_health():
        return {"ok": True, "version": __version__, "name": "diffdesk"}

    @app.get("/api/dashboard")
    async def api_dashboard():
        return database.dashboard()

    @app.get("/api/reviews")
    async def api_list_reviews(
        status: Optional[str] = None,
        risk: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = Query(100, ge=1, le=500),
    ):
        return database.list_reviews(status=status, risk=risk, q=q, limit=limit)

    @app.post("/api/reviews", status_code=201)
    async def api_create_review(body: ReviewCreate):
        return database.create_review(body)

    @app.get("/api/reviews/{review_id}")
    async def api_get_review(review_id: int):
        review = database.get_review(review_id)
        if not review:
            raise HTTPException(404, "Review not found")
        return review

    @app.patch("/api/reviews/{review_id}")
    async def api_update_review(review_id: int, body: ReviewUpdate):
        review = database.update_review(review_id, body)
        if not review:
            raise HTTPException(404, "Review not found")
        return review

    @app.post("/api/reviews/{review_id}/decision")
    async def api_decision(review_id: int, body: DecisionRequest):
        try:
            review = database.set_decision(review_id, body)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not review:
            raise HTTPException(404, "Review not found")
        return review

    @app.delete("/api/reviews/{review_id}")
    async def api_delete_review(review_id: int):
        if not database.delete_review(review_id):
            raise HTTPException(404, "Review not found")
        return {"ok": True}

    @app.patch("/api/checklist/{item_id}")
    async def api_checklist(item_id: int, body: ChecklistUpdate):
        item = database.update_checklist_item(item_id, body.status, body.notes)
        if not item:
            raise HTTPException(404, "Checklist item not found")
        return item

    @app.post("/api/reviews/{review_id}/findings", status_code=201)
    async def api_add_finding(review_id: int, body: FindingCreate):
        finding = database.add_finding(review_id, body)
        if not finding:
            raise HTTPException(404, "Review not found")
        return finding

    @app.patch("/api/findings/{finding_id}")
    async def api_update_finding(finding_id: int, body: FindingUpdate):
        finding = database.update_finding(finding_id, body)
        if not finding:
            raise HTTPException(404, "Finding not found")
        return finding

    @app.delete("/api/findings/{finding_id}")
    async def api_delete_finding(finding_id: int):
        if not database.delete_finding(finding_id):
            raise HTTPException(404, "Finding not found")
        return {"ok": True}

    @app.get("/api/settings")
    async def api_settings():
        return {
            "checklist_template": database.get_checklist_template(),
            "db_path": str(database.path),
            "version": __version__,
        }

    @app.put("/api/settings/checklist")
    async def api_settings_checklist(body: SettingsUpdate):
        return {"checklist_template": database.update_checklist_template(body.checklist_template)}

    @app.post("/api/seed")
    async def api_seed(force: bool = False):
        return database.seed_demo(force=force)

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: HTTPException):  # type: ignore[override]
        accept = request.headers.get("accept", "")
        if "text/html" in accept and not request.url.path.startswith("/api/"):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "active": "",
                    "page_title": "Not found",
                    "error_code": 404,
                    "error_message": "That page does not exist.",
                },
                status_code=404,
            )
        return JSONResponse({"detail": "Not found"}, status_code=404)

    return app


# Module-level app for uvicorn `diffdesk.app:app`
app = create_app()
