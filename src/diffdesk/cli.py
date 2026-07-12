"""CLI entrypoint for diffdesk."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from diffdesk import __version__
from diffdesk.db import Database, default_db_path

app = typer.Typer(
    name="diffdesk",
    help="Local-first web app for reviewing AI-authored code changes.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print version."""
    console.print(f"diffdesk {__version__}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8788, help="Bind port"),
    reload: bool = typer.Option(False, help="Auto-reload (dev)"),
    db: Optional[Path] = typer.Option(None, help="SQLite database path"),
) -> None:
    """Launch the diffdesk web app."""
    if db:
        os.environ["DIFFDESK_DB"] = str(Path(db).expanduser().resolve())
    db_path = default_db_path()
    # ensure schema
    Database(db_path)
    console.print(f"[bold cyan]diffdesk[/] {__version__}")
    console.print(f"  UI   → [link=http://{host}:{port}/]http://{host}:{port}/[/link]")
    console.print(f"  API  → http://{host}:{port}/api/reviews")
    console.print(f"  DB   → {db_path}")
    import uvicorn

    uvicorn.run(
        "diffdesk.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command()
def seed(
    force: bool = typer.Option(False, "--force", "-f", help="Seed even if data exists"),
    db: Optional[Path] = typer.Option(None, help="SQLite database path"),
) -> None:
    """Load demo review sessions."""
    if db:
        os.environ["DIFFDESK_DB"] = str(Path(db).expanduser().resolve())
    database = Database()
    result = database.seed_demo(force=force)
    if result.get("seeded"):
        console.print(f"[green]Seeded[/] {result['count']} demo reviews: {result.get('ids')}")
    else:
        console.print(f"[yellow]Skipped[/] ({result.get('reason')}). Use --force to re-seed.")


@app.command("list")
def list_reviews(
    status: Optional[str] = typer.Option(None, help="Filter status"),
    db: Optional[Path] = typer.Option(None, help="SQLite database path"),
) -> None:
    """List reviews in the local store."""
    if db:
        os.environ["DIFFDESK_DB"] = str(Path(db).expanduser().resolve())
    database = Database()
    rows = database.list_reviews(status=status)
    table = Table(title="diffdesk reviews")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Risk")
    table.add_column("Files")
    table.add_column("Findings")
    for r in rows:
        table.add_row(
            str(r["id"]),
            r["title"][:48],
            r["status"],
            r["risk"],
            str(r["file_count"]),
            str(r["finding_count"]),
        )
    console.print(table)
    if not rows:
        console.print("[dim]No reviews yet. Run: diffdesk seed[/]")


@app.command()
def init(
    db: Optional[Path] = typer.Option(None, help="SQLite database path"),
) -> None:
    """Initialize the local database and default checklist template."""
    if db:
        os.environ["DIFFDESK_DB"] = str(Path(db).expanduser().resolve())
    database = Database()
    tpl = database.get_checklist_template()
    console.print(f"[green]Ready[/] database at {database.path}")
    console.print(f"Checklist template items: {len(tpl)}")


if __name__ == "__main__":
    app()
