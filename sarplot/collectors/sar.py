"""Historical system metrics, read from sysstat archives via ``sadf``.

``sadf -j`` renders a binary ``sa`` archive as JSON. The exact shape of each
sample depends on which ``sar`` flag was requested, and it has changed between
sysstat releases (for example the timestamp gained a ``tz`` key in 12.7 where
older builds emitted ``utc``). Rather than hard-coding one schema, this module
discovers the payload key at runtime and flattens whatever it finds, which
lets a single code path serve CPU, memory, swap, load, I/O, disk, network and
paging metrics.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

SADF_BINARY = "sadf"

#: Distributions disagree on where sysstat keeps its archives: Debian/Ubuntu
#: use /var/log/sysstat, RHEL/Fedora/Alma use /var/log/sa.
LOG_DIRECTORIES = ("/var/log/sysstat", "/var/log/sa")

#: Give up on a slow archive rather than freezing the UI thread forever.
SADF_TIMEOUT_SECONDS = 30

#: Separator between a device/CPU identity and its field, e.g. "all/user".
IDENTITY_SEPARATOR = "/"

#: Separator for nested dictionaries, e.g. "io-reads.rtps".
NESTED_SEPARATOR = "."

_SA_NAME_RE = re.compile(r"^sa(?P<digits>\d{2}|\d{8})$")


class SarError(RuntimeError):
    """Raised when sar history cannot be read."""


class SarUnavailable(SarError):
    """Raised when sysstat is not installed or has collected nothing yet."""


@dataclass(frozen=True)
class MetricSpec:
    """A selectable metric, and the ``sar`` flags that produce it."""

    key: str
    label: str
    flags: tuple[str, ...]
    unit: str = ""
    #: Substrings used to pick sensible initial series when the user has not
    #: chosen any. Matched against the flattened series name.
    preferred: tuple[str, ...] = ()
    #: Clamp the y-axis, for metrics that are inherently percentages.
    ylim: tuple[float, float] | None = None
    description: str = ""


METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(
        key="cpu",
        label="CPU",
        flags=("-u",),
        unit="%",
        preferred=("all/busy", "all/user", "all/system", "all/iowait"),
        ylim=(0, 100),
        description="Aggregate CPU utilisation breakdown.",
    ),
    MetricSpec(
        key="cpu-per-core",
        label="CPU (per core)",
        flags=("-u", "-P", "ALL"),
        unit="%",
        preferred=("/busy",),
        ylim=(0, 100),
        description="Per-core CPU utilisation.",
    ),
    MetricSpec(
        key="memory",
        label="Memory",
        flags=("-r",),
        unit="kB",
        # Kept unit-consistent: mixing a percentage with kB values flattens
        # the percentage against a multi-million-unit axis.
        preferred=("memused", "avail", "cached", "buffers"),
        description="Memory utilisation.",
    ),
    MetricSpec(
        key="swap",
        label="Swap",
        flags=("-S",),
        unit="kB",
        preferred=("swpused", "swpfree", "swpcad"),
        description="Swap space utilisation.",
    ),
    MetricSpec(
        key="load",
        label="Load & run queue",
        flags=("-q",),
        preferred=("ldavg-1", "ldavg-5", "ldavg-15"),
        description="Load average, run queue and blocked task counts.",
    ),
    MetricSpec(
        key="io",
        label="I/O transfer",
        flags=("-b",),
        preferred=("tps", "io-reads.rtps", "io-writes.wtps"),
        description="Aggregate block I/O rates.",
    ),
    MetricSpec(
        key="disk",
        label="Block devices",
        flags=("-d",),
        preferred=("/tps", "/util-percent"),
        description="Per-device block I/O activity.",
    ),
    MetricSpec(
        key="network",
        label="Network",
        flags=("-n", "DEV"),
        unit="kB/s",
        preferred=("/rxkB", "/txkB"),
        description="Per-interface network throughput.",
    ),
    MetricSpec(
        key="paging",
        label="Paging",
        flags=("-B",),
        preferred=("pgpgin", "pgpgout", "majflt"),
        description="Paging and page fault activity.",
    ),
    MetricSpec(
        key="swap-pages",
        label="Swap paging",
        flags=("-W",),
        preferred=("pswpin", "pswpout"),
        description="Pages swapped in and out.",
    ),
)

METRICS_BY_KEY: dict[str, MetricSpec] = {m.key: m for m in METRICS}


@dataclass(frozen=True)
class LogFile:
    """A sysstat archive on disk."""

    path: Path
    day: date | None

    @property
    def label(self) -> str:
        if self.day is not None:
            return f"{self.day.isoformat()}  ({self.path.name})"
        return self.path.name


@dataclass
class TimeSeries:
    """Timestamped samples, keyed by flattened series name."""

    timestamps: list[datetime] = field(default_factory=list)
    columns: dict[str, list[float | None]] = field(default_factory=dict)
    nodename: str = ""

    def __bool__(self) -> bool:
        return bool(self.timestamps and self.columns)

    @property
    def names(self) -> list[str]:
        """Series names, sorted for stable presentation."""
        return sorted(self.columns)

    def points(self, name: str) -> tuple[list[datetime], list[float]]:
        """Return the non-null points for one series.

        Devices can appear or disappear mid-archive, so a series may be
        sparse. Gaps are dropped rather than plotted as zero, which would
        misrepresent the data.
        """
        values = self.columns.get(name)
        if values is None:
            return [], []

        stamps: list[datetime] = []
        points: list[float] = []
        for stamp, value in zip(self.timestamps, values, strict=False):
            if value is not None:
                stamps.append(stamp)
                points.append(value)
        return stamps, points

    def indexed(self, name: str) -> tuple[list[int], list[float]]:
        """Return non-null points as ``(position, value)`` pairs.

        Positions index into `timestamps`, so a sparse series stays aligned
        with a shared time axis instead of being compressed toward zero.
        """
        values = self.columns.get(name)
        if values is None:
            return [], []

        positions: list[int] = []
        points: list[float] = []
        for index, value in enumerate(values):
            if value is not None:
                positions.append(index)
                points.append(value)
        return positions, points


def has_sadf() -> bool:
    """Whether the ``sadf`` binary is installed."""
    return shutil.which(SADF_BINARY) is not None


def is_available() -> bool:
    """Whether ``sadf`` exists and at least one archive is readable."""
    return has_sadf() and bool(list_log_files())


def missing_reason() -> str:
    """A human-readable explanation of why history is unavailable."""
    if not has_sadf():
        return "The 'sadf' command was not found. Install sysstat to enable historical metrics."
    searched = ", ".join(LOG_DIRECTORIES)
    return (
        f"No sysstat archives found in {searched}. Enable collection so sar "
        "can begin recording, then check back shortly."
    )


def _parse_archive_day(name: str, fallback: Path) -> date | None:
    """Derive the date an archive covers from its filename.

    ``saDD`` only encodes the day of month, so the month and year are taken
    from the file's modification time.
    """
    match = _SA_NAME_RE.match(name)
    if match is None:
        return None

    digits = match.group("digits")
    try:
        if len(digits) == 8:
            return datetime.strptime(digits, "%Y%m%d").date()

        mtime = datetime.fromtimestamp(fallback.stat().st_mtime)
        return mtime.date().replace(day=int(digits))
    except (ValueError, OSError):
        return None


def list_log_files() -> list[LogFile]:
    """Discover sysstat archives, newest first."""
    found: list[LogFile] = []
    seen: set[Path] = set()

    for directory in LOG_DIRECTORIES:
        base = Path(directory)
        if not base.is_dir():
            continue

        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue

        for entry in entries:
            if not entry.is_file() or entry.name in seen:
                continue
            if _SA_NAME_RE.match(entry.name) is None:
                continue
            seen.add(entry.name)
            found.append(LogFile(entry, _parse_archive_day(entry.name, entry)))

    found.sort(key=lambda f: (f.day is not None, f.day, f.path.name), reverse=True)
    return found


def _run_sadf(path: str, flags: tuple[str, ...], start: str, end: str) -> str:
    """Invoke ``sadf`` and return raw JSON, translating failures to SarError."""
    command = [SADF_BINARY, "-j", path, "--", *flags]
    if start:
        command += ["-s", start]
    if end:
        command += ["-e", end]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=SADF_TIMEOUT_SECONDS,
            check=True,
        )
    except FileNotFoundError as exc:
        raise SarUnavailable(missing_reason()) from exc
    except subprocess.TimeoutExpired as exc:
        raise SarError(f"sadf timed out after {SADF_TIMEOUT_SECONDS}s reading {path}.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or f"exit status {exc.returncode}"
        raise SarError(f"sadf failed: {detail}") from exc

    return result.stdout


@lru_cache(maxsize=32)
def _cached_sadf(path: str, flags: tuple[str, ...], start: str, end: str) -> str:
    """Memoised ``sadf`` output.

    Switching which series are plotted must not re-read the archive, which can
    take seconds on a full day of samples.
    """
    return _run_sadf(path, flags, start, end)


def clear_cache() -> None:
    """Drop memoised ``sadf`` output, so a growing archive is re-read."""
    _cached_sadf.cache_clear()


def _parse_timestamp(raw: dict) -> datetime | None:
    """Build a datetime from a sadf timestamp object.

    Tolerates both the modern ``tz`` key and the older ``utc`` flag, neither of
    which is needed to place the sample on a time axis.
    """
    day = raw.get("date")
    clock = raw.get("time")
    if not day or not clock:
        return None
    try:
        return datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _coerce(value: object) -> float | None:
    """Convert a JSON scalar to a float, or None if it is not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _identity_of(entry: dict) -> str | None:
    """Find the field naming the device/CPU a record describes.

    sadf marks these consistently as the sole string-valued field: ``cpu`` for
    cpu-load, ``disk-device`` for disk, ``iface`` for net-dev.
    """
    for key, value in entry.items():
        if isinstance(value, str):
            return key
    return None


def _flatten(payload: object, prefix: str = "") -> dict[str, float]:
    """Flatten one sample's payload into ``{series name: value}``.

    Handles the four shapes sadf emits:

    * list of records -> ``identity/field`` (cpu-load, disk)
    * dict of nested lists -> descends (network -> net-dev)
    * dict of nested dicts -> ``parent.child`` (io -> io-reads.rtps)
    * flat dict -> ``field`` (memory, queue, paging)
    """
    flat: dict[str, float] = {}

    if isinstance(payload, list):
        for record in payload:
            if not isinstance(record, dict):
                continue
            identity_key = _identity_of(record)
            identity = record.get(identity_key) if identity_key else None
            for key, value in record.items():
                if key == identity_key:
                    continue
                if identity:
                    # A device name is globally meaningful on its own, so it
                    # replaces any container prefix: "net-dev" + "eth0" + "rxkB"
                    # reads better as "eth0/rxkB".
                    name = f"{identity}{IDENTITY_SEPARATOR}{key}"
                elif prefix:
                    name = f"{prefix}{NESTED_SEPARATOR}{key}"
                else:
                    name = key
                flat.update(_flatten(value, name))
        return flat

    if isinstance(payload, dict):
        for key, value in payload.items():
            nested = f"{prefix}{NESTED_SEPARATOR}{key}" if prefix else key
            flat.update(_flatten(value, nested))
        return flat

    number = _coerce(payload)
    if number is not None and prefix:
        flat[prefix] = number
    return flat


def _add_derived(flat: dict[str, float]) -> None:
    """Add convenience series that sar does not report directly.

    ``idle`` is inverted into ``busy`` because "how loaded was this box" is the
    usual question, and it is what the original implementation plotted.
    """
    for name, value in list(flat.items()):
        if name == "idle":
            flat["busy"] = 100.0 - value
        elif name.endswith(f"{IDENTITY_SEPARATOR}idle"):
            stem = name[: -len("idle")]
            flat[f"{stem}busy"] = 100.0 - value


def parse(raw: str) -> TimeSeries:
    """Parse ``sadf -j`` output into a :class:`TimeSeries`."""
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SarError(f"sadf returned malformed JSON: {exc}") from exc

    try:
        hosts = document["sysstat"]["hosts"]
    except (KeyError, TypeError) as exc:
        raise SarError("Unexpected sadf output: no 'sysstat.hosts' key.") from exc

    if not hosts:
        return TimeSeries()

    host = hosts[0]
    series = TimeSeries(nodename=host.get("nodename", ""))

    # sadf pads the array with empty objects around restarts and file
    # boundaries; they carry no samples.
    samples = [s for s in host.get("statistics", []) if s]

    for index, sample in enumerate(samples):
        stamp = _parse_timestamp(sample.get("timestamp", {}))
        if stamp is None:
            continue

        flat: dict[str, float] = {}
        for key, payload in sample.items():
            if key == "timestamp":
                continue
            flat.update(_flatten(payload))
        _add_derived(flat)

        series.timestamps.append(stamp)
        for name, value in flat.items():
            column = series.columns.get(name)
            if column is None:
                # Back-fill so every column stays aligned with `timestamps`.
                column = [None] * index
                series.columns[name] = column
            column.append(value)

        # Pad series absent from this sample, e.g. a device that went away.
        for name, column in series.columns.items():
            if name not in flat:
                column.append(None)

    return series


def query(
    path: str | Path,
    metric: MetricSpec,
    start: str = "",
    end: str = "",
    *,
    use_cache: bool = True,
) -> TimeSeries:
    """Read one metric from an archive over an optional time window.

    Args:
        path: Archive to read, e.g. ``/var/log/sysstat/sa30``.
        metric: Which metric to request.
        start: Inclusive start time as ``HH:MM:SS``. Empty means "from the top".
        end: Exclusive end time as ``HH:MM:SS``. Empty means "to the end".
        use_cache: Serve from the memoised ``sadf`` output when available.

    Raises:
        SarUnavailable: sysstat is not installed.
        SarError: the archive is missing, unreadable or malformed.
    """
    archive = Path(path)
    if not archive.exists():
        raise SarError(f"Archive not found: {archive}")

    runner = _cached_sadf if use_cache else _run_sadf
    return parse(runner(str(archive), tuple(metric.flags), start, end))


def choose_default_series(series: TimeSeries, metric: MetricSpec, limit: int = 4) -> list[str]:
    """Pick a useful initial selection of series for a metric.

    Patterns are matched in tiers - exact, then identity-suffix, then suffix,
    then substring - so ``tps`` prefers the aggregate over ``io-discard.dtps``
    and ``ldavg-1`` does not swallow ``ldavg-15``.

    Descent stops as soon as every pattern has matched, which keeps the
    selection unit-consistent: without it, a loose substring pass would pad
    the list with ``swpused-percent`` alongside absolute kB series, flattening
    the percentage against a multi-million-unit axis.

    Falls back to the first few series alphabetically so a metric with an
    unrecognised schema still renders something.
    """
    names = series.names
    if not names:
        return []

    chosen: list[str] = []
    matched: set[str] = set()

    matchers = (
        lambda name, pattern: name == pattern,
        lambda name, pattern: name.endswith(f"{IDENTITY_SEPARATOR}{pattern}"),
        lambda name, pattern: name.endswith(pattern),
        lambda name, pattern: pattern in name,
    )

    for matches in matchers:
        for pattern in metric.preferred:
            for name in names:
                if not matches(name, pattern):
                    continue
                matched.add(pattern)
                if name not in chosen:
                    chosen.append(name)
                if len(chosen) >= limit:
                    return chosen
        if matched and len(matched) == len(metric.preferred):
            break

    return chosen or names[:limit]
