"""Local CLI: python3 -m giftcard_tool --help."""
from __future__ import annotations

import argparse
import functools
import json
import shutil
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from .pipeline import ValidationError, atomic_write, iso, read_json, run_pipeline, utcnow

ROOT = Path(__file__).resolve().parents[1]


def demo(output: Path) -> dict:
    batch = read_json(ROOT / "fixtures/demo-batch.json")
    if batch.get("demo") is not True:
        raise ValidationError("Only synthetic fixtures may have their dates rebased")
    batch["observed_at"] = iso(utcnow())
    batch["run_id"] = "demo-" + uuid4().hex[:16]
    batch_path = output / "input.json"
    atomic_write(batch_path, batch)
    # A demo run is disposable; use its own database to avoid mixing fixture reruns.
    result = run_pipeline(ROOT / "config/retailers.json", batch_path,
                          output / "snapshot.json", output / "history.sqlite3")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Gift-card advertised-discount snapshots")
    sub = parser.add_subparsers(dest="command", required=True)
    demo_parser = sub.add_parser("demo", help="Build a clearly labeled synthetic snapshot")
    demo_parser.add_argument("--output", type=Path, default=Path("build/demo"))
    importer = sub.add_parser("import", help="Validate our interchange JSON, record history, publish locally")
    importer.add_argument("input", type=Path)
    importer.add_argument("--catalog", type=Path, default=ROOT / "config/retailers.json")
    importer.add_argument("--output", type=Path, default=Path("build/import/snapshot.json"))
    importer.add_argument("--database", type=Path, default=Path("build/import/history.sqlite3"))
    importer.add_argument("--max-age-hours", type=int, default=48)
    collector = sub.add_parser("collect", help="Collect public GCX advertised discounts without purchasing")
    collector.add_argument("--catalog", type=Path, default=ROOT / "config/retailers-live.json")
    collector.add_argument("--output", type=Path, default=Path("build/live/input.json"))
    collector.add_argument("--max-pages", type=int, default=20)
    collector.add_argument("--request-budget", type=int, default=20)
    lookup = sub.add_parser(
        "lookup",
        help="Look up one reviewed retailer's advertised max GCX discount and purchase-page link",
    )
    lookup.add_argument("query", help="Retailer id, name, domain, or GCX path fragment (e.g. dominos)")
    lookup.add_argument("--catalog", type=Path, default=ROOT / "config/retailers-live.json")
    lookup.add_argument("--max-pages", type=int, default=20)
    lookup.add_argument("--request-budget", type=int, default=20)
    preview = sub.add_parser("preview", help="Run the interactive local demo; no Xcode or AWS required")
    preview.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "collect":
            from .gcx import collect_batch
            batch = collect_batch(read_json(args.catalog), max_pages=args.max_pages,
                                  request_budget=args.request_budget)
            atomic_write(args.output, batch)
            print(json.dumps({"output": str(args.output), "retailers": len(batch["offers"]), "demo": False}))
        elif args.command == "lookup":
            from .gcx import lookup_offers
            rows = lookup_offers(
                read_json(args.catalog),
                args.query,
                max_pages=args.max_pages,
                request_budget=args.request_budget,
            )
            print(json.dumps(rows if len(rows) > 1 else rows[0], indent=2))
        elif args.command == "demo":
            print(json.dumps(demo(args.output), indent=2))
        elif args.command == "import":
            print(json.dumps(run_pipeline(args.catalog, args.input, args.output,
                                          args.database, max_age_hours=args.max_age_hours), indent=2))
        else:
            workspace = ROOT / "build/preview-data"
            demo(workspace)
            public = ROOT / "build/preview-public"
            public.mkdir(parents=True, exist_ok=True)
            for name in ("index.html", "preview.js", "preview.css"):
                shutil.copy2(ROOT / "preview" / name, public / name)
            for name in ("core.js", "ui.js"):
                shutil.copy2(ROOT / "extension" / name, public / name)
            shutil.copy2(workspace / "snapshot.json", public / "snapshot.json")
            handler = functools.partial(SimpleHTTPRequestHandler, directory=str(public))
            server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
            print(f"Demo: http://127.0.0.1:{args.port}/ (synthetic data; Ctrl-C to stop)", flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
    except KeyboardInterrupt:
        return 0
    except (ValidationError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
