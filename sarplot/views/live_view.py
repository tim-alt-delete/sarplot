"""Live, continuously sampled metrics."""

from __future__ import annotations

import time

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Select, Static
from textual_plotext import PlotextPlot

from sarplot.collectors import live

#: Metric key -> (label, y-axis unit, fixed y-limits or None).
LIVE_METRICS: dict[str, tuple[str, str, tuple[float, float] | None]] = {
    "cpu": ("CPU total", "%", (0, 100)),
    "cpu-per-core": ("CPU per core", "%", (0, 100)),
    "memory": ("Memory & swap", "%", (0, 100)),
    "network": ("Network throughput", "kB/s", None),
}


class LiveView(Vertical):
    """Plot live metrics sampled on a timer.

    The timer is paused while the view is off-screen so a hidden tab does not
    keep waking the process every second.
    """

    def __init__(self, *, interval: float = 1.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._interval = interval
        self._history = live.RollingSeries()
        self._metric = "cpu"
        self._timer = None
        self._previous_counters: dict[str, float] = {}
        self._previous_time = 0.0
        self._primed = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="live-controls"):
            yield Label("Metric", classes="control-label")
            yield Select(
                [(label, key) for key, (label, _, _) in LIVE_METRICS.items()],
                value="cpu",
                allow_blank=False,
                id="live-metric-select",
            )
            yield Static("", id="live-readout")
        yield PlotextPlot(id="live-plot")

    def on_mount(self) -> None:
        self._timer = self.set_interval(self._interval, self._tick)

    @on(Select.Changed, "#live-metric-select")
    def _on_metric_changed(self, event: Select.Changed) -> None:
        self._metric = str(event.value)
        # Samples from the previous metric are not comparable.
        self._history.clear()
        self._previous_counters = {}
        self._primed = False
        self._tick()

    def pause(self) -> None:
        """Stop sampling, e.g. when the tab is hidden."""
        if self._timer is not None:
            self._timer.pause()

    def resume(self) -> None:
        """Resume sampling when the tab becomes visible again."""
        if self._timer is not None:
            self._timer.resume()

    def _collect(self) -> dict[str, float]:
        if self._metric == "cpu":
            return live.sample_cpu()
        if self._metric == "cpu-per-core":
            return live.sample_cpu(per_core=True)
        if self._metric == "memory":
            return live.sample_memory()
        if self._metric == "network":
            now = time.monotonic()
            current = live.sample_network()
            if not self._previous_counters:
                self._previous_counters = current
                self._previous_time = now
                return {}
            elapsed = now - self._previous_time
            rate = live.rates(self._previous_counters, current, elapsed)
            self._previous_counters = current
            self._previous_time = now
            return rate
        return {}

    def _tick(self) -> None:
        samples = self._collect()

        # psutil's non-blocking cpu_percent compares against the previous call,
        # so the very first reading after startup is meaningless.
        if not self._primed:
            self._primed = True
            if self._metric.startswith("cpu"):
                return

        if samples:
            self._history.push(samples)
        self._draw()

    def _draw(self) -> None:
        label, unit, ylim = LIVE_METRICS.get(self._metric, ("", "", None))
        plot = self.query_one("#live-plot", PlotextPlot)
        plt = plot.plt
        plt.clear_figure()

        names = self._history.names
        if not names or len(self._history) == 0:
            plt.title(f"{label} - sampling...")
            plot.refresh()
            return

        readout: list[str] = []
        for name in names:
            values = self._history.values(name)
            if values:
                plt.plot(values, label=name)
                readout.append(f"{name} {values[-1]:.1f}{unit}")

        plt.title(f"{label} ({unit})" if unit else label)
        if ylim is not None:
            plt.ylim(*ylim)
        plot.refresh()

        # Per-core readouts would overflow the control bar.
        if len(readout) <= 4:
            self.query_one("#live-readout", Static).update("   ".join(readout))
        else:
            self.query_one("#live-readout", Static).update(f"{len(readout)} series")
