"""systemd journal support - partially implemented.

.. note::

   **This module is a scaffold. Journal browsing is not yet wired into the
   Logs tab.**

   The pure functions here are implemented and tested, because they need
   neither a running journald nor a subprocess:

   * :func:`is_available` / :func:`missing_reason` - detection
   * :data:`PRIORITY_TO_LEVEL` - syslog severity mapping
   * :func:`parse_json_line` / :func:`parse_json_stream` - ``-o json`` parsing

   TODO: remaining work to finish journald support.

   1. Implement :func:`read` on top of
      ``journalctl -n N --no-pager -o json``.
   2. Implement :func:`follow` as a ``journalctl -f -o json`` subprocess
      streamed from a thread worker, mirroring ``HistoryView._load``. The
      child must be terminated when the tab is hidden or the app exits,
      otherwise a background tab leaves a journalctl process running.
   3. Add a ``JournalSource`` implementing
      :class:`sarplot.collectors.logs.LogSource` so the view can consume it
      without changes.
   4. Show it as a pinned entry above the directory tree, and prefer it in
      ``logs.default_log`` when no classic syslog file exists.
   5. Replace the synthetic test fixtures with real captured output (see the
      caveat below).

.. warning::

   The fixtures in ``tests/fixtures/journal/`` are **synthetic**. They were
   written from the documented systemd journal field schema, not captured
   from a live system: the development machine runs ``tini`` as PID 1, so
   journald never starts and there is no journal to read even as root.
   Unlike ``tests/fixtures/*.json`` for sar - which are real ``sadf`` output
   from sysstat 12.7.7 - these have not been checked against a real
   ``journalctl``. Verify them on a systemd host before relying on them.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sarplot.collectors.logs import Level, LogLine

JOURNALCTL_BINARY = "journalctl"

#: journald stores logs in one of these, depending on Storage= in
#: journald.conf. Persistent journals live under /var/log, volatile ones
#: under /run and vanish on reboot.
JOURNAL_DIRECTORIES = ("/var/log/journal", "/run/log/journal")

#: syslog severities (RFC 5424), as reported in the journal's PRIORITY field.
PRIORITY_TO_LEVEL: dict[int, Level] = {
    0: Level.CRITICAL,  # emerg
    1: Level.CRITICAL,  # alert
    2: Level.CRITICAL,  # crit
    3: Level.ERROR,  # err
    4: Level.WARNING,  # warning
    5: Level.NOTICE,  # notice
    6: Level.INFO,  # info
    7: Level.DEBUG,  # debug
}


class JournalError(RuntimeError):
    """Raised when the journal cannot be read."""


class JournalUnavailable(JournalError):
    """Raised when journalctl is missing or there is no journal to read."""


@dataclass(frozen=True)
class JournalEntry:
    """One journal record, reduced to the fields worth displaying."""

    timestamp: datetime | None
    message: str
    identifier: str = ""
    pid: str = ""
    hostname: str = ""
    unit: str = ""
    level: Level | None = None

    def format(self) -> str:
        """Render in the familiar ``short-iso`` style journalctl uses."""
        stamp = self.timestamp.strftime("%Y-%m-%dT%H:%M:%S") if self.timestamp else "-"
        source = self.identifier or self.unit or "?"
        pid = f"[{self.pid}]" if self.pid else ""
        host = f" {self.hostname}" if self.hostname else ""
        return f"{stamp}{host} {source}{pid}: {self.message}"

    def to_log_line(self) -> LogLine:
        return LogLine(self.format(), self.level)


def has_journalctl() -> bool:
    """Whether the ``journalctl`` binary is installed."""
    return shutil.which(JOURNALCTL_BINARY) is not None


def has_journal_files() -> bool:
    """Whether any journal actually exists on disk.

    Checked separately from the binary because ``journalctl`` is installed as
    part of systemd on hosts where journald never runs - in a container with a
    non-systemd init, for example.
    """
    for directory in JOURNAL_DIRECTORIES:
        base = Path(directory)
        if not base.is_dir():
            continue
        try:
            if any(base.iterdir()):
                return True
        except OSError:
            continue
    return False


def is_available() -> bool:
    """Whether journal entries could be read.

    Both conditions are required. ``journalctl`` exits **0** with an empty
    journal, printing ``-- No entries --`` to stdout and ``No journal files
    were found.`` to stderr, so neither the binary's presence nor the exit
    status can be used on its own.
    """
    return has_journalctl() and has_journal_files()


def missing_reason() -> str:
    """A human-readable explanation of why the journal is unavailable."""
    if not has_journalctl():
        return (
            "The 'journalctl' command was not found, so this host does not use the systemd journal."
        )
    if not has_journal_files():
        searched = " or ".join(JOURNAL_DIRECTORIES)
        return (
            f"journalctl is installed but no journal exists in {searched}. "
            "journald is probably not running on this host."
        )
    return ""


def _coerce_message(raw: object) -> str:
    """Decode a MESSAGE field.

    systemd emits a list of byte values instead of a string when a message is
    not valid UTF-8.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        try:
            return bytes(raw).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            return ""
    if raw is None:
        return ""
    return str(raw)


def _coerce_timestamp(raw: object) -> datetime | None:
    """Convert __REALTIME_TIMESTAMP, microseconds since the epoch as a string."""
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(int(raw) / 1_000_000)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _coerce_level(raw: object) -> Level | None:
    try:
        return PRIORITY_TO_LEVEL.get(int(raw))
    except (TypeError, ValueError):
        return None


def parse_json_line(line: str) -> JournalEntry | None:
    """Parse one line of ``journalctl -o json`` output.

    Returns None for blank lines and malformed records, so a single bad entry
    cannot abort a whole stream.
    """
    line = line.strip()
    if not line:
        return None

    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None

    return JournalEntry(
        timestamp=_coerce_timestamp(record.get("__REALTIME_TIMESTAMP")),
        message=_coerce_message(record.get("MESSAGE")),
        identifier=str(record.get("SYSLOG_IDENTIFIER") or record.get("_COMM") or ""),
        pid=str(record.get("_PID") or ""),
        hostname=str(record.get("_HOSTNAME") or ""),
        unit=str(record.get("_SYSTEMD_UNIT") or ""),
        level=_coerce_level(record.get("PRIORITY")),
    )


def parse_json_stream(text: str) -> list[JournalEntry]:
    """Parse newline-delimited ``journalctl -o json`` output."""
    entries = []
    for line in text.splitlines():
        entry = parse_json_line(line)
        if entry is not None:
            entries.append(entry)
    return entries


def read(lines: int = 500) -> list[LogLine]:
    """Read the most recent journal entries.

    TODO: not implemented. See the module docstring.
    """
    raise NotImplementedError(
        "Journal reading is not implemented yet; see the TODO in sarplot/collectors/journal.py."
    )


def follow():
    """Stream new journal entries as they arrive.

    TODO: not implemented. See the module docstring.
    """
    raise NotImplementedError(
        "Journal following is not implemented yet; see the TODO in sarplot/collectors/journal.py."
    )
