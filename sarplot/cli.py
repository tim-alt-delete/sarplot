"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys

from sarplot import __version__
from sarplot.app import DEFAULT_TAB, SarPlot
from sarplot.collectors import logs
from sarplot.views.history_view import normalise_time

TAB_CHOICES = {
    "processes": "tab-processes",
    "live": "tab-live",
    "history": "tab-history",
    "logs": "tab-logs",
    "system": "tab-system",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sarplot",
        description=("A terminal dashboard for live system metrics and sysstat (sar) history."),
        epilog=("Historical metrics require sysstat. Without it, the live tabs still work."),
    )
    parser.add_argument(
        "-f",
        "--file",
        metavar="PATH",
        help="sysstat archive to open, e.g. /var/log/sysstat/sa30. "
        "Defaults to the most recent archive found.",
    )
    parser.add_argument(
        "-s",
        "--start",
        default="",
        metavar="HH:MM:SS",
        help="Start of the historical time window.",
    )
    parser.add_argument(
        "-e",
        "--end",
        default="",
        metavar="HH:MM:SS",
        help="End of the historical time window.",
    )
    parser.add_argument(
        "-r",
        "--refresh",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Process list refresh interval (default: %(default)s).",
    )
    parser.add_argument(
        "-t",
        "--tab",
        choices=sorted(TAB_CHOICES),
        default="processes",
        help="Tab to open on startup (default: %(default)s).",
    )
    parser.add_argument(
        "-L",
        "--log-file",
        metavar="PATH",
        help="Log file to open in the Logs tab. Defaults to the system log, "
        "falling back to the most recent readable file in the log directory.",
    )
    parser.add_argument(
        "-D",
        "--log-dir",
        metavar="DIR",
        default=logs.DEFAULT_LOG_DIR,
        help="Directory the log explorer is rooted at (default: %(default)s).",
    )
    parser.add_argument(
        "--log-lines",
        type=int,
        default=5000,
        metavar="N",
        help="Log lines retained in memory (default: %(default)s).",
    )
    parser.add_argument("-V", "--version", action="version", version=f"sarplot {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.refresh <= 0:
        parser.error("--refresh must be greater than zero")

    if args.log_lines < 1:
        parser.error("--log-lines must be at least 1")

    start = normalise_time(args.start)
    if start is None:
        parser.error(f"--start: invalid time {args.start!r}, expected HH:MM or HH:MM:SS")

    end = normalise_time(args.end)
    if end is None:
        parser.error(f"--end: invalid time {args.end!r}, expected HH:MM or HH:MM:SS")

    if start and end and start >= end:
        parser.error("--start must be earlier than --end")

    app = SarPlot(
        sa_file=args.file,
        start=start,
        end=end,
        refresh=args.refresh,
        initial_tab=TAB_CHOICES.get(args.tab, DEFAULT_TAB),
        log_file=args.log_file,
        log_dir=args.log_dir,
        log_lines=args.log_lines,
    )
    app.run()
    return app.return_code or 0


if __name__ == "__main__":
    sys.exit(main())
