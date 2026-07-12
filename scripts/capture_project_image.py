#!/usr/bin/env python3
"""Capture a live screenshot of the diffdesk UI for docs/images/project.png."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "project.png"
PORT = 8791
DB = Path("/tmp/diffdesk-screenshot.db")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()

    env = os.environ.copy()
    env["DIFFDESK_DB"] = str(DB)
    subprocess.check_call([sys.executable, "-m", "diffdesk", "seed"], cwd=ROOT, env=env)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "diffdesk.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2.0)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
            # open first review detail if present for multi-panel shot
            for a in page.locator('a[href^="/reviews/"]').all():
                href = a.get_attribute("href") or ""
                if href.startswith("/reviews/") and href not in ("/reviews", "/reviews/new") and href.count("/") >= 2:
                    page.goto(f"http://127.0.0.1:{PORT}{href}", wait_until="networkidle")
                    break
            page.screenshot(path=str(OUT), full_page=False)
            browser.close()
        print("wrote", OUT, "size", OUT.stat().st_size)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
