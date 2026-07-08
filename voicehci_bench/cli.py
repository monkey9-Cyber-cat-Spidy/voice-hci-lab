"""voicehci-bench CLI.

    voicehci-bench dataset            # (re)generate data/voicehci_bench_v1.jsonl
    voicehci-bench run                # all systems -> results/latest.json + REPORT.md
    voicehci-bench run --systems thought-stream,final-cleaned
    voicehci-bench serve              # dashboard at http://localhost:8765
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import shutil
from pathlib import Path

from .dataset import DEFAULT_PATH, generate_dataset, save_dataset
from .report import render_markdown
from .runner import run_benchmark
from .systems import ACTION_SYSTEMS, DICTATION_SYSTEMS

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
DASHBOARD = Path(__file__).resolve().parent / "dashboard" / "index.html"


def cmd_dataset(args: argparse.Namespace) -> int:
    recs = generate_dataset(seed=args.seed)
    p = save_dataset(recs, DEFAULT_PATH)
    from collections import Counter

    print(f"wrote {len(recs)} records -> {p}")
    for cat, n in sorted(Counter(r.category for r in recs).items()):
        print(f"  {cat:<17} {n}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    systems = args.systems.split(",") if args.systems else None
    payload = run_benchmark(systems=systems, out_dir=RESULTS)
    md = render_markdown(payload)
    (RESULTS / "REPORT.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"results -> {RESULTS / 'latest.json'}  ({payload['meta']['wall_seconds']} s)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:  # pragma: no cover - interactive
    RESULTS.mkdir(exist_ok=True)
    shutil.copy(DASHBOARD, RESULTS / "index.html")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(RESULTS))
    print(f"dashboard: http://localhost:{args.port}/  (Ctrl+C to stop)")
    with (http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as srv,
          contextlib.suppress(KeyboardInterrupt)):
        srv.serve_forever()
    return 0


def cmd_systems(args: argparse.Namespace) -> int:
    for n in DICTATION_SYSTEMS:
        print(f"dictation  {n}")
    for n in ACTION_SYSTEMS:
        print(f"action     {n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="voicehci-bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dataset")
    d.add_argument("--seed", type=int, default=7)
    d.set_defaults(fn=cmd_dataset)
    r = sub.add_parser("run")
    r.add_argument("--systems", default="")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_serve)
    ls = sub.add_parser("systems")
    ls.set_defaults(fn=cmd_systems)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
