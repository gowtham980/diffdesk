# ROADMAP — diffdesk

## v0.1 (shipped)
- Local-first FastAPI + SQLite web app
- Multi-view shell: Dashboard, Reviews, New Review, Review detail, Settings
- Multi-panel review desk: files | diff | checklist + findings
- Unified diff parser (multi-file)
- Default AI-slop checklist template (editable)
- Ship / request changes / archive decisions
- REST JSON API for agents
- CLI: `serve`, `seed`, `list`, `init`, `version`
- Demo seed data
- Tests for parser + API + decisions

## v0.2
- Import from `git diff` path / PR patch URL (local fetch only)
- Syntax highlighting via highlight.js or pygments
- Keyboard navigation across files (`j`/`k`) and checklist toggles
- Bulk mark checklist pass/fail
- Export review session as Markdown / JSON report
- Dark/light theme toggle

## v0.3
- Optional GitHub / GitLab read-only patch import (token in local settings)
- Side-by-side diff mode
- Review templates per project (`.diffdesk.yml`)
- Finding suggestions from simple heuristics (secrets regex, TODO, bare except)
- Agent webhook: POST diff → open review session id

## Later
- Multi-user local auth (still self-hosted)
- Annotation pins on diff lines
- Compare two agent runs for the same task
- Mobile-optimized review queue
