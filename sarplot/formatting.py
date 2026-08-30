"""Human-readable formatting helpers."""

from __future__ import annotations

_BYTE_UNITS = ("B", "K", "M", "G", "T", "P", "E", "Z", "Y")


def format_bytes(num: float, precision: int = 1) -> str:
    """Format a byte count using binary (1024-based) unit prefixes.

    Args:
        num: Number of bytes. Negative values are formatted with a leading `-`.
        precision: Digits after the decimal point.

    Returns:
        A short string such as `"1.5G"`. Values too large for the largest
        known prefix are clamped to that prefix rather than returning `None`.
    """
    sign = "-" if num < 0 else ""
    value = float(abs(num))

    for unit in _BYTE_UNITS:
        if value < 1024:
            return f"{sign}{value:.{precision}f}{unit}"
        value /= 1024

    # Ran off the end of the prefix table: undo the last division and clamp to
    # the largest known unit. The previous implementation fell out of the loop
    # and implicitly returned None.
    return f"{sign}{value * 1024:.{precision}f}{_BYTE_UNITS[-1]}"


def format_cpu_time(seconds: float) -> str:
    """Format cumulative CPU time the way `top`/`htop` do.

    Renders as `MM:SS.hh`, widening to `HH:MM:SS` once the total reaches an
    hour so long-lived processes stay readable.
    """
    if seconds < 0:
        seconds = 0.0

    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"

    hundredths = int((seconds - total) * 100)
    return f"{minutes:02d}:{secs:02d}.{hundredths:02d}"


def format_percent(value: float, precision: int = 1) -> str:
    """Format a percentage without a trailing `%` (column headers carry it)."""
    return f"{value:.{precision}f}"


def format_uptime(seconds: float) -> str:
    """Format an uptime duration as `NNd NNh NNm`."""
    seconds = max(0.0, seconds)
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}m"
