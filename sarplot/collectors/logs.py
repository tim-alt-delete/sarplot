"""Reading and following log files.

Kept free of any Textual imports so the tailing logic can be tested directly.

Files are read by seeking backwards from the end rather than reading the whole
file: a system log can be hundreds of megabytes, and a naive read would stall
the UI for seconds every refresh.
"""

from __future__ import annotations

import bz2
import gzip
import lzma
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import IO, Protocol, runtime_checkable

#: Read backwards in chunks of this size when tailing.
BLOCK_SIZE = 8192

#: Bytes inspected when deciding whether a file is binary.
PROBE_SIZE = 8192

#: Above this share of non-text bytes in the probe, treat the file as binary.
BINARY_RATIO = 0.30

#: Default directory the file explorer is rooted at.
DEFAULT_LOG_DIR = "/var/log"

#: Candidate system logs, most specific first. Distributions disagree:
#: Debian/Ubuntu use syslog, RHEL/Alma/Fedora use messages.
SYSTEM_LOG_CANDIDATES = (
    "/var/log/syslog",
    "/var/log/messages",
    "/var/log/system.log",
)

#: Suffixes handled transparently by the stdlib compression modules.
COMPRESSED_SUFFIXES = {".gz": gzip.open, ".xz": lzma.open, ".bz2": bz2.open}

#: Well-known binary logs. These hold fixed-width C structs, and an empty one
#: passes a content probe, so they are excluded by name as well.
BINARY_NAMES = frozenset({"wtmp", "btmp", "utmp", "lastlog", "faillog", "tallylog"})

#: Rotated logs keep the original name plus a numeric or compressed suffix.
_ROTATED_RE = re.compile(r"\.(?:\d+)(?:\.(?:gz|xz|bz2))?$")

_TEXT_BYTES = frozenset(bytes(range(32, 127)) + b"\n\r\t\f\b\x1b")


class LogError(RuntimeError):
    """Raised when a log file cannot be read."""


class Level(Enum):
    """Severity, shared by the file and journal sources."""

    DEBUG = "debug"
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


#: Matched case-insensitively against each line, first hit wins. Ordered so
#: that the more severe patterns are tested before the weaker ones.
_LEVEL_PATTERNS: tuple[tuple[Level, re.Pattern[str]], ...] = (
    (Level.CRITICAL, re.compile(r"\b(critical|crit|fatal|panic|emerg|alert)\b", re.I)),
    (Level.ERROR, re.compile(r"\b(error|err|failed|failure|segfault)\b", re.I)),
    (Level.WARNING, re.compile(r"\b(warning|warn)\b", re.I)),
    (Level.NOTICE, re.compile(r"\b(notice)\b", re.I)),
    (Level.INFO, re.compile(r"\b(info)\b", re.I)),
    (Level.DEBUG, re.compile(r"\b(debug|trace)\b", re.I)),
)


@dataclass(frozen=True, slots=True)
class LogLine:
    """One line of a log, with its detected severity."""

    text: str
    level: Level | None = None


def detect_level(text: str) -> Level | None:
    """Guess a line's severity from its text.

    Best-effort only: plain text logs have no standard severity field, so this
    matches common keywords. The journal source uses the authoritative
    PRIORITY field instead of guessing.
    """
    for level, pattern in _LEVEL_PATTERNS:
        if pattern.search(text):
            return level
    return None


def is_compressed(path: Path) -> bool:
    return path.suffix.lower() in COMPRESSED_SUFFIXES


def looks_binary(path: Path) -> bool:
    """Whether a file appears to hold binary rather than text data.

    /var/log routinely contains wtmp, lastlog and sysstat archives, all of
    which render as noise if opened as text.

    Raises:
        LogError: the file cannot be read.
    """
    # Checked before reading: these are binary even when zero bytes long,
    # which a content probe cannot tell apart from an empty text log.
    if path.name.split(".")[0] in BINARY_NAMES:
        return True

    try:
        if is_compressed(path):
            with _open_compressed(path) as handle:
                chunk = handle.read(PROBE_SIZE)
        else:
            with path.open("rb") as handle:
                chunk = handle.read(PROBE_SIZE)
    except (OSError, EOFError, lzma.LZMAError) as exc:
        raise LogError(_describe_os_error(path, exc)) from exc

    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    nontext = sum(1 for byte in chunk if byte not in _TEXT_BYTES)
    return nontext / len(chunk) > BINARY_RATIO


def _open_compressed(path: Path) -> IO[bytes]:
    opener = COMPRESSED_SUFFIXES[path.suffix.lower()]
    return opener(path, "rb")


def _describe_os_error(path: Path, exc: Exception) -> str:
    """Turn a filesystem error into something worth showing a user."""
    if isinstance(exc, PermissionError):
        return f"Permission denied reading {path}. Most system logs require root."
    if isinstance(exc, FileNotFoundError):
        return f"{path} no longer exists."
    if isinstance(exc, IsADirectoryError):
        return f"{path} is a directory."
    return f"Could not read {path}: {exc}"


def is_readable(path: Path) -> bool:
    """Whether the file can actually be opened, not merely stat-ed."""
    return os.access(path, os.R_OK) and path.is_file()


def is_rotated_name(path: Path) -> bool:
    """Whether a filename looks like a rotated log (``syslog.1``, ``.2.gz``)."""
    return _ROTATED_RE.search(path.name) is not None


def decode(raw: bytes) -> str:
    """Decode a log line.

    Logs routinely contain invalid UTF-8 from truncated writes or binary
    payloads, so replacement is the only workable policy.
    """
    return raw.decode("utf-8", errors="replace")


def split_lines(raw: bytes) -> list[str]:
    """Split a byte blob into decoded lines without keeping the terminators."""
    if not raw:
        return []
    return [decode(line) for line in raw.splitlines()]


def tail_bytes(path: Path, lines: int) -> tuple[bytes, int]:
    """Read approximately the last ``lines`` lines of a file.

    Returns the raw bytes and the file size they were read up to, so a
    follower can continue from exactly that offset.

    Seeks backwards in blocks instead of reading the file, which keeps this
    O(lines) rather than O(filesize).
    """
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()

        if lines <= 0 or size == 0:
            return b"", size

        end = size
        data = b""
        # One extra newline so a full first line is captured rather than a
        # fragment of the line above it.
        while end > 0 and data.count(b"\n") <= lines:
            start = max(0, end - BLOCK_SIZE)
            handle.seek(start)
            data = handle.read(end - start) + data
            end = start

        collected = data.splitlines()[-lines:]
        return b"\n".join(collected), size


@runtime_checkable
class LogSource(Protocol):
    """A thing that can produce log lines.

    The seam that lets a journald source be added later without reworking the
    view; see sarplot/collectors/journal.py.
    """

    @property
    def name(self) -> str:
        """A short label for the status line."""

    @property
    def followable(self) -> bool:
        """Whether new lines can appear after the initial read."""

    def read_initial(self, lines: int) -> list[LogLine]:
        """Read the most recent ``lines`` lines."""

    def read_new(self) -> list[LogLine]:
        """Read lines appended since the last call."""

    def close(self) -> None:
        """Release any resources."""


@dataclass
class FileSource:
    """Tails a single log file, tolerating rotation and truncation."""

    path: Path
    _offset: int = field(default=0, init=False)
    _inode: int | None = field(default=None, init=False)
    _rotated: bool = field(default=False, init=False)

    @property
    def name(self) -> str:
        return str(self.path)

    @property
    def followable(self) -> bool:
        # A compressed archive is a fixed snapshot; nothing will be appended.
        return not is_compressed(self.path)

    @property
    def rotated_since_last_read(self) -> bool:
        """Whether the previous read_new() observed a rotation or truncation."""
        return self._rotated

    def close(self) -> None:  # pragma: no cover - nothing held open
        return None

    def _stat(self) -> os.stat_result:
        try:
            return self.path.stat()
        except OSError as exc:
            raise LogError(_describe_os_error(self.path, exc)) from exc

    def read_initial(self, lines: int) -> list[LogLine]:
        """Read the tail of the file and remember where it ended."""
        self._rotated = False

        if is_compressed(self.path):
            return self._read_compressed(lines)

        if looks_binary(self.path):
            raise LogError(f"{self.path.name} looks like a binary file, not a text log.")

        try:
            raw, size = tail_bytes(self.path, lines)
        except OSError as exc:
            raise LogError(_describe_os_error(self.path, exc)) from exc

        self._offset = size
        self._inode = self._stat().st_ino
        return [LogLine(text, detect_level(text)) for text in split_lines(raw)]

    def _read_compressed(self, lines: int) -> list[LogLine]:
        """Decompress and keep the last ``lines`` lines.

        There is no way to seek backwards through a compressed stream, so the
        whole file is streamed, but only a bounded window is retained.
        """
        from collections import deque

        try:
            with _open_compressed(self.path) as handle:
                window: deque[bytes] = deque(handle.read().splitlines(), maxlen=lines)
        except (OSError, EOFError, lzma.LZMAError) as exc:
            raise LogError(_describe_os_error(self.path, exc)) from exc

        self._offset = 0
        self._inode = None
        return [LogLine(text, detect_level(text)) for text in (decode(line) for line in window)]

    def read_new(self) -> list[LogLine]:
        """Read whatever has been appended since the last read.

        Handles the two ways a log stops being the file we were reading:
        rotation (the name now points at a new inode) and truncation
        (logrotate's copytruncate, or ``> logfile``).
        """
        self._rotated = False

        if not self.followable:
            return []

        stat = self._stat()

        if self._inode is not None and stat.st_ino != self._inode:
            # Rotated: the path now refers to a different file. Anything left
            # unread in the old one is gone, so start from the new file's top.
            self._rotated = True
            self._offset = 0
            self._inode = stat.st_ino
        elif stat.st_size < self._offset:
            # Truncated in place.
            self._rotated = True
            self._offset = 0

        if stat.st_size <= self._offset:
            return []

        try:
            with self.path.open("rb") as handle:
                handle.seek(self._offset)
                raw = handle.read(stat.st_size - self._offset)
        except OSError as exc:
            raise LogError(_describe_os_error(self.path, exc)) from exc

        self._offset += len(raw)
        self._inode = stat.st_ino
        return [LogLine(text, detect_level(text)) for text in split_lines(raw)]


def discover_system_log(candidates: Iterable[str] = SYSTEM_LOG_CANDIDATES) -> Path | None:
    """Find the primary system log.

    Returns None when no classic syslog file exists, which is the norm on
    systemd hosts that log only to the journal.
    """
    for candidate in candidates:
        path = Path(candidate)
        if is_readable(path):
            return path
    return None


def list_readable_logs(directory: str | Path = DEFAULT_LOG_DIR) -> list[Path]:
    """Readable, non-binary text logs directly inside ``directory``.

    Used as a last-resort default when no recognised system log exists.
    """
    base = Path(directory)
    if not base.is_dir():
        return []

    found: list[Path] = []
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return []

    for entry in entries:
        if not is_readable(entry):
            continue
        try:
            if looks_binary(entry):
                continue
        except LogError:
            continue
        found.append(entry)
    return found


def default_log(directory: str | Path = DEFAULT_LOG_DIR) -> Path | None:
    """The file the Logs tab should open with.

    Prefers a real system log, then falls back to the most recently modified
    readable text file so the tab opens on something useful.
    """
    system = discover_system_log()
    if system is not None:
        return system

    candidates = [p for p in list_readable_logs(directory) if not is_rotated_name(p)]
    if not candidates:
        return None

    def modified(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    return max(candidates, key=modified)
