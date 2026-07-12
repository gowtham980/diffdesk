#!/usr/bin/env python3
"""Generate docs/images/project.png — mock of the diffdesk multi-panel UI."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


W, H = 1280, 720
OUT = Path(__file__).resolve().parents[1] / "docs" / "images" / "project.png"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width: int = 1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    bg = (11, 15, 23)
    panel = (21, 28, 44)
    panel2 = (18, 24, 38)
    border = (36, 48, 73)
    text = (232, 238, 252)
    muted = (147, 160, 184)
    accent = (110, 168, 255)
    accent2 = (139, 124, 255)
    success = (62, 207, 142)
    danger = (255, 107, 122)
    warn = (245, 185, 66)

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    # soft glows
    for cx, cy, col in [(180, 40, (40, 70, 120)), (1100, 80, (70, 50, 120))]:
        for r, a in [(220, 28), (140, 18)]:
            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            od.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*col, a))
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
            d = ImageDraw.Draw(img)

    # sidebar
    rounded(d, (24, 24, 250, H - 24), 16, (12, 17, 28), border)
    # brand
    rounded(d, (44, 48, 78, 82), 10, accent)
    d.text((50, 55), "dd", fill=(11, 15, 23), font=font(14, True))
    d.text((90, 50), "diffdesk", fill=text, font=font(18, True))
    d.text((90, 72), "AI review workspace", fill=muted, font=font(11))

    nav = [
        (True, "Dashboard"),
        (False, "Reviews"),
        (False, "New review"),
        (False, "Settings"),
    ]
    y = 120
    for active, label in nav:
        if active:
            rounded(d, (40, y - 6, 234, y + 28), 10, (28, 48, 82))
            d.text((56, y), "◈  " + label, fill=accent, font=font(14, True))
        else:
            d.text((56, y), "·  " + label, fill=muted, font=font(14))
        y += 42

    d.text((48, H - 70), "v0.1.0 · local-first", fill=(90, 100, 120), font=font(11))

    # top bar
    rounded(d, (268, 24, W - 24, 78), 14, panel2, border)
    d.text((292, 42), "Review · Agent: add rate limiter to API", fill=text, font=font(16, True))
    rounded(d, (W - 180, 38, W - 44, 66), 8, accent)
    d.text((W - 168, 44), "+ New review", fill=(11, 15, 23), font=font(12, True))

    # badges
    bx = 292
    for label, col in [("IN REVIEW", accent2), ("RISK HIGH", danger), ("agent", muted)]:
        tw = 12 * len(label) // 2 + 28
        rounded(d, (bx, 96, bx + tw, 118), 10, (*col[:3],) if False else (30, 36, 52), col)
        # solid badge bg approx
        rounded(d, (bx, 96, bx + tw, 118), 10, (28, 34, 50), col)
        d.text((bx + 10, 100), label, fill=col, font=font(10, True))
        bx += tw + 10

    # decision buttons
    for i, (label, col) in enumerate(
        [("Mark ship", success), ("Request changes", warn), ("Archive", muted)]
    ):
        x0 = 292 + i * 150
        rounded(d, (x0, 132, x0 + 138, 158), 8, (24, 32, 48), col)
        d.text((x0 + 16, 138), label, fill=col, font=font(11, True))

    # three panels
    left = (268, 180, 470, H - 36)
    mid = (486, 180, 900, H - 36)
    right = (916, 180, W - 24, H - 36)

    for box in (left, mid, right):
        rounded(d, box, 14, panel, border)

    # file list
    d.text((286, 196), "FILES", fill=muted, font=font(11, True))
    files = [
        ("rate_limit.py", True, "+28", "−0"),
        ("main.py", False, "+9", "−1"),
    ]
    fy = 230
    for name, active, a, b in files:
        if active:
            rounded(d, (282, fy - 6, 456, fy + 42), 8, (28, 48, 82), accent)
        d.text((294, fy), name, fill=text if active else muted, font=font(12, True))
        d.text((294, fy + 18), f"python  {a}  {b}", fill=success if active else muted, font=font(10))
        fy += 58

    # diff panel
    d.text((506, 196), "DIFF", fill=muted, font=font(11, True))
    d.text((506, 218), "app/middleware/rate_limit.py", fill=text, font=font(12, True))
    diff_lines = [
        ("meta", "@@ -0,0 +1,28 @@"),
        ("add", "+REDIS_URL = \"redis://:supersecret@...\""),
        ("add", "+class RateLimiter:"),
        ("ctx", "     def allow(self, key):"),
        ("add", "+        if len(bucket) >= self.limit:"),
        ("del", "-        return True"),
        ("add", "+        return False"),
        ("ctx", " def get_limiter():"),
        ("add", "+    return RateLimiter()"),
    ]
    dy = 250
    for kind, line in diff_lines:
        if kind == "add":
            d.rectangle((500, dy - 2, 886, dy + 16), fill=(24, 48, 40))
            col = success
        elif kind == "del":
            d.rectangle((500, dy - 2, 886, dy + 16), fill=(52, 28, 34))
            col = danger
        elif kind == "meta":
            col = accent
        else:
            col = (180, 190, 210)
        d.text((512, dy), line[:52], fill=col, font=font(11))
        dy += 22

    # checklist / findings
    d.text((936, 196), "AI CHECKLIST", fill=muted, font=font(11, True))
    checks = [
        ("correctness", "pass", success),
        ("security", "fail", danger),
        ("secrets", "fail", danger),
        ("tests", "todo", muted),
    ]
    cy = 224
    for cat, st, col in checks:
        rounded(d, (932, cy, W - 40, cy + 36), 8, (18, 24, 36), border)
        d.text((944, cy + 10), f"{cat}", fill=text, font=font(11, True))
        d.text((W - 100, cy + 10), st, fill=col, font=font(11, True))
        cy += 44

    d.text((936, cy + 8), "FINDINGS", fill=muted, font=font(11, True))
    rounded(d, (932, cy + 32, W - 40, cy + 100), 8, (40, 24, 28), danger)
    d.text((944, cy + 44), "HIGH  Hard-coded Redis password", fill=danger, font=font(11, True))
    d.text((944, cy + 66), "Move secret to env + rotate", fill=muted, font=font(10))

    # footer tagline
    d.text(
        (292, H - 28),
        "Local-first multi-panel desk for reviewing AI-authored code",
        fill=(80, 90, 110),
        font=font(11),
    )

    img.save(OUT, "PNG", optimize=True)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
