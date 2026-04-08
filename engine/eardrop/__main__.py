from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path
from queue import Queue

from .config import Config
from .database import Database


def cmd_watch(args: argparse.Namespace, config: Config) -> None:
    """Start the watcher daemon — monitors inbox and processes new audio files."""
    from .watcher import Watcher
    from .worker import Worker

    db = Database(config)
    db.init_schema()

    queue: Queue[Path] = Queue()
    worker = Worker(config, db, queue)
    watcher = Watcher(config, queue)

    def shutdown(sig, frame):
        print("\nShutting down...")
        watcher.stop()
        worker.stop()
        db.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    worker.start()
    watcher.start()

    print(f"Eardrop watching {config.watch_dir}")
    print("Press Ctrl+C to stop")

    # Block main thread
    signal.pause()


def cmd_process(args: argparse.Namespace, config: Config) -> None:
    """Process a single audio file."""
    from .pipeline import process_recording

    path = Path(args.file).resolve()
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    db = Database(config)
    db.init_schema()

    try:
        recording_id = process_recording(path, config, db)
        print(f"Done. Recording ID: {recording_id}")
    finally:
        db.close()


def cmd_search(args: argparse.Namespace, config: Config) -> None:
    """Search transcripts by keyword."""
    db = Database(config)
    db.init_schema()

    try:
        results = db.search_transcripts(args.query)
        if not results:
            print("No results found.")
            return

        for r in results:
            print(f"\n--- {r['filename']} ({r['recorded_at']}) ---")
            print(r["snippet"])
    finally:
        db.close()


def cmd_ask(args: argparse.Namespace, config: Config) -> None:
    """Ask a question about your transcripts."""
    from .querier import query

    db = Database(config)
    db.init_schema()

    try:
        answer = query(args.question, db, config)
        print(answer)
    finally:
        db.close()


def cmd_status(args: argparse.Namespace, config: Config) -> None:
    """Show recent recordings and processing status."""
    db = Database(config)
    db.init_schema()

    try:
        recordings = db.list_recordings(limit=20)
        if not recordings:
            print("No recordings yet.")
            return

        for rec in recordings:
            status_icon = {
                "pending": ".",
                "transcribing": ">",
                "diarizing": ">",
                "summarizing": ">",
                "complete": "+",
                "error": "!",
            }.get(rec.status, "?")

            duration = f"{rec.duration_seconds:.0f}s" if rec.duration_seconds else "?"
            date = rec.recorded_at.strftime("%Y-%m-%d %H:%M") if rec.recorded_at else "?"
            print(f"  [{status_icon}] {rec.filename}  {duration}  {date}  ({rec.status})")

            if rec.status == "error" and rec.error_message:
                print(f"      Error: {rec.error_message}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="eardrop",
        description="Personal audio transcription and summarization",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("watch", help="Watch inbox for new audio files")

    p_process = sub.add_parser("process", help="Process a single audio file")
    p_process.add_argument("file", help="Path to audio file")

    p_search = sub.add_parser("search", help="Search transcripts")
    p_search.add_argument("query", help="Search query")

    p_ask = sub.add_parser("ask", help="Ask a question about your transcripts")
    p_ask.add_argument("question", help="Natural language question")

    sub.add_parser("status", help="Show recent recordings")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = Config()
    config.ensure_dirs()

    commands = {
        "watch": cmd_watch,
        "process": cmd_process,
        "search": cmd_search,
        "ask": cmd_ask,
        "status": cmd_status,
    }
    commands[args.command](args, config)


if __name__ == "__main__":
    main()
