"""Unified diff parser for multi-file patches."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedFile:
    path: str
    language: str
    patch: str
    additions: int = 0
    deletions: int = 0
    old_path: str | None = None


@dataclass
class ParseResult:
    files: list[ParsedFile] = field(default_factory=list)
    raw: str = ""
    warnings: list[str] = field(default_factory=list)


_DIFF_GIT = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_DIFF_CLASSIC = re.compile(r"^---\s+(?:a/)?(.+?)(?:\t.*)?$")
_PLUS_PLUS = re.compile(r"^\+\+\+\s+(?:b/)?(.+?)(?:\t.*)?$")
_RENAME_FROM = re.compile(r"^rename from (.+)$")
_RENAME_TO = re.compile(r"^rename to (.+)$")
_NEW_FILE = re.compile(r"^new file mode")
_DELETED = re.compile(r"^deleted file mode")


def guess_language(path: str) -> str:
    """Best-effort language guess from file extension."""
    lower = path.lower().rsplit("/", 1)[-1]
    if "." not in lower:
        if lower in {"dockerfile", "makefile", "gemfile", "rakefile"}:
            return lower
        return "text"
    ext = lower.rsplit(".", 1)[-1]
    mapping = {
        "py": "python",
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "go": "go",
        "rs": "rust",
        "java": "java",
        "kt": "kotlin",
        "rb": "ruby",
        "php": "php",
        "c": "c",
        "h": "c",
        "cpp": "cpp",
        "cc": "cpp",
        "hpp": "cpp",
        "cs": "csharp",
        "swift": "swift",
        "m": "objective-c",
        "mm": "objective-c",
        "sh": "bash",
        "bash": "bash",
        "zsh": "bash",
        "ps1": "powershell",
        "sql": "sql",
        "md": "markdown",
        "json": "json",
        "yml": "yaml",
        "yaml": "yaml",
        "toml": "toml",
        "ini": "ini",
        "cfg": "ini",
        "css": "css",
        "scss": "scss",
        "html": "html",
        "htm": "html",
        "xml": "xml",
        "vue": "vue",
        "svelte": "svelte",
        "dart": "dart",
        "r": "r",
        "lua": "lua",
        "ex": "elixir",
        "exs": "elixir",
        "erl": "erlang",
        "hs": "haskell",
        "scala": "scala",
        "clj": "clojure",
        "dockerfile": "dockerfile",
        "tf": "hcl",
        "hcl": "hcl",
    }
    return mapping.get(ext, ext)


def _count_hunk_stats(lines: list[str]) -> tuple[int, int]:
    adds = dels = 0
    for line in lines:
        if line.startswith("+") and not line.startswith("+++"):
            adds += 1
        elif line.startswith("-") and not line.startswith("---"):
            dels += 1
    return adds, dels


def parse_unified_diff(text: str) -> ParseResult:
    """Parse a unified / git-style multi-file diff into file patches.

    Handles:
    - `diff --git a/x b/y` headers
    - classic `---` / `+++` headers
    - renames, new/deleted files
    - empty input (returns empty file list)
    """
    result = ParseResult(raw=text or "")
    if not text or not text.strip():
        return result

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Ensure trailing content is captured
    if lines and lines[-1] != "":
        lines.append("")

    current: list[str] = []
    path: str | None = None
    old_path: str | None = None
    pending_old: str | None = None

    def flush() -> None:
        nonlocal current, path, old_path, pending_old
        if path is None and not current:
            pending_old = None
            return
        if path is None:
            # Try extract from current buffer
            for ln in current:
                m = _PLUS_PLUS.match(ln)
                if m and m.group(1) not in {"/dev/null"}:
                    path = m.group(1)
                    break
                m2 = _DIFF_CLASSIC.match(ln)
                if m2 and m2.group(1) not in {"/dev/null"}:
                    path = m2.group(1)
            if path is None:
                result.warnings.append("Could not determine path for a diff hunk; skipped.")
                current = []
                old_path = None
                pending_old = None
                return
        patch = "\n".join(current).rstrip("\n")
        adds, dels = _count_hunk_stats(current)
        result.files.append(
            ParsedFile(
                path=path,
                language=guess_language(path),
                patch=patch + ("\n" if patch else ""),
                additions=adds,
                deletions=dels,
                old_path=old_path,
            )
        )
        current = []
        path = None
        old_path = None
        pending_old = None

    i = 0
    while i < len(lines):
        line = lines[i]
        m_git = _DIFF_GIT.match(line)
        if m_git:
            flush()
            old_path = m_git.group(1)
            path = m_git.group(2)
            if path == "/dev/null":
                path = old_path  # deleted file — keep old path
            current = [line]
            i += 1
            continue

        m_classic = _DIFF_CLASSIC.match(line)
        # Start of classic file header only if not already inside a git block without +++
        if m_classic and (not current or current[0].startswith("---") or path is None):
            # If we already have content for another file, flush first
            if current and path is not None:
                flush()
            elif current and any(x.startswith("@@") for x in current):
                flush()
            pending_old = m_classic.group(1)
            if pending_old == "/dev/null":
                pending_old = None
            current = [line]
            i += 1
            if i < len(lines):
                m_plus = _PLUS_PLUS.match(lines[i])
                if m_plus:
                    new_p = m_plus.group(1)
                    if new_p == "/dev/null":
                        path = pending_old or "deleted"
                    else:
                        path = new_p
                        old_path = pending_old
                    current.append(lines[i])
                    i += 1
                    continue
            path = pending_old or "unknown"
            continue

        m_plus = _PLUS_PLUS.match(line)
        if m_plus and current:
            new_p = m_plus.group(1)
            if new_p != "/dev/null":
                path = new_p
            elif pending_old:
                path = pending_old
            current.append(line)
            i += 1
            continue

        if current is not None and (current or path is not None):
            # Continue current file patch
            if line.startswith("diff --git "):
                # shouldn't reach (handled above)
                pass
            current.append(line)
        i += 1

    flush()

    # Drop empty-path noise
    result.files = [f for f in result.files if f.path and f.path != "unknown"]
    return result


def render_diff_html_lines(patch: str) -> list[dict]:
    """Turn a patch into structured lines for UI rendering.

    Each item: {type: meta|hunk|add|del|ctx|other, text: str}
    """
    out: list[dict] = []
    if not patch:
        return out
    for line in patch.splitlines():
        if line.startswith("@@"):
            out.append({"type": "hunk", "text": line})
        elif line.startswith("+++") or line.startswith("---") or line.startswith("diff "):
            out.append({"type": "meta", "text": line})
        elif line.startswith("index ") or line.startswith("new file") or line.startswith(
            "deleted file"
        ) or line.startswith("similarity ") or line.startswith("rename "):
            out.append({"type": "meta", "text": line})
        elif line.startswith("+"):
            out.append({"type": "add", "text": line})
        elif line.startswith("-"):
            out.append({"type": "del", "text": line})
        elif line.startswith("\\"):
            out.append({"type": "meta", "text": line})
        else:
            # context lines often start with space
            out.append({"type": "ctx", "text": line})
    return out
