"""Live system metrics sampled through psutil."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import psutil

#: Roughly a minute of history at the default one-second cadence.
DEFAULT_HISTORY = 120


@dataclass
class RollingSeries:
    """A fixed-length ring buffer of samples, one series per name."""

    capacity: int = DEFAULT_HISTORY
    _series: dict[str, deque[float]] = field(default_factory=dict, repr=False)

    def push(self, samples: dict[str, float]) -> None:
        """Append one reading for each named series."""
        for name, value in samples.items():
            buffer = self._series.get(name)
            if buffer is None:
                buffer = deque(maxlen=self.capacity)
                self._series[name] = buffer
            buffer.append(value)

    def values(self, name: str) -> list[float]:
        return list(self._series.get(name, ()))

    @property
    def names(self) -> list[str]:
        return sorted(self._series)

    def __len__(self) -> int:
        return max((len(b) for b in self._series.values()), default=0)

    def clear(self) -> None:
        self._series.clear()


def sample_cpu(per_core: bool = False) -> dict[str, float]:
    """Sample CPU utilisation since the previous call.

    ``interval=None`` makes this non-blocking, comparing against the previous
    call rather than sleeping. The first sample after startup is therefore
    meaningless and should be discarded by the caller.
    """
    if per_core:
        return {
            f"cpu{index}": value
            for index, value in enumerate(psutil.cpu_percent(interval=None, percpu=True))
        }
    return {"total": psutil.cpu_percent(interval=None)}


def sample_memory() -> dict[str, float]:
    """Sample memory and swap utilisation as percentages."""
    virtual = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {"memory": virtual.percent, "swap": swap.percent}


def sample_network() -> dict[str, float]:
    """Sample cumulative network counters, in kilobytes."""
    counters = psutil.net_io_counters()
    if counters is None:
        return {}
    return {
        "sent": counters.bytes_sent / 1024,
        "received": counters.bytes_recv / 1024,
    }


def rates(
    previous: dict[str, float], current: dict[str, float], seconds: float
) -> dict[str, float]:
    """Convert cumulative counters into per-second rates.

    Counter resets (an interface disappearing, or a wrap) yield a negative
    delta; those are reported as zero rather than a nonsensical spike.
    """
    if seconds <= 0:
        return dict.fromkeys(current, 0.0)
    return {
        name: max(0.0, (value - previous.get(name, value)) / seconds)
        for name, value in current.items()
    }
