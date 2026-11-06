"""Command-line interface: python -m xops_core."""
from __future__ import annotations

import argparse
import json
import sys

from .store import add_posts, connect, counts, export_approved, find_posts, initialize, review
from .validators import ValidationError, load_document, validate_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="XOps Core: local, human-reviewed content pipeline")
    parser.add_argument("--db", default="./xops-core.sqlite3", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize local database")
    importing = sub.add_parser("import", help="Import PUBLIC_POSTS_V1 JSON / fenced JSON")
    importing.add_argument("file")
    listing = sub.add_parser("list", help="List candidate posts")
    listing.add_argument("--status", choices=["pending", "approved", "rejected", "exported"])
    reviewing = sub.add_parser("review", help="Review one candidate by row number")
    reviewing.add_argument("id", type=int)
    reviewing.add_argument("decision", choices=["approve", "reject"])
    exporting = sub.add_parser("export", help="Write approved posts to JSON (never publishes)")
    exporting.add_argument("file")
    exporting.add_argument("--keep-approved", action="store_true")
    sub.add_parser("stats", help="Count posts by status")
    serving = sub.add_parser("serve", help="Launch local-only human review web interface")
    serving.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        with connect(args.db) as conn:
            initialize(conn)
            if args.command == "init":
                print(f"Initialized local database: {args.db}")
            elif args.command == "import":
                posts = validate_document(load_document(args.file))
                print(json.dumps(add_posts(conn, posts), ensure_ascii=False))
            elif args.command == "list":
                for row in find_posts(conn, args.status):
                    body = json.loads(row["body"])
                    print(f"{row['id']:>4}  {row['status']:<9}  {row['account']:<8}  {row['event_id']:<35}  {body['text'][:60]}")
            elif args.command == "review":
                review(conn, args.id, "approved" if args.decision == "approve" else "rejected")
                print(f"Reviewed #{args.id}: {args.decision}")
            elif args.command == "export":
                total = export_approved(conn, args.file, args.keep_approved)
                print(f"Exported {total} approved posts to {args.file}" if total else "No approved posts; file unchanged")
            elif args.command == "stats":
                print(json.dumps(counts(conn), ensure_ascii=False))
            elif args.command == "serve":
                if not 1 <= args.port <= 65535:
                    raise ValidationError("Port must be between 1 and 65535")
                from .webui import serve
                serve(args.db, args.port)
    except (ValidationError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
