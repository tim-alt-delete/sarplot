"""Browse historical metrics recorded by sysstat."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, Label, Select, SelectionList, Static
from textual_plotext import PlotextPlot

from sarplot.collectors import sar

#: Accepts H:M, HH:MM or HH:MM:SS, which sadf's -s/-e options understand.
_TIME_RE = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")

#: Beyond a handful of overlaid series the plot legend becomes unreadable.
MAX_PLOTTED_SERIES = 8


def normalise_time(value: str) -> str | None:
    """Validate a user-supplied time, returning it as ``HH:MM:SS``.

    Returns None if the value is not a valid time. An empty string is valid
    and means "unbounded", so it is returned unchanged.
    """
    value = value.strip()
    if not value:
        return ""
    if _TIME_RE.match(value) is None:
        return None
    parts = value.split(":")
    if len(parts) == 2:
        parts.append("00")
    return ":".join(part.zfill(2) for part in parts)


@dataclass
class QueryRequest:
    """A resolved, validated request for historical data."""

    path: Path
    metric: sar.MetricSpec
    start: str
    end: str


class HistoryView(Vertical):
    """Query sysstat archives and plot the results.

    Degrades to an explanatory panel when sysstat is absent, rather than
    letting a subprocess failure propagate into the app.
    """

    class Loaded(Message):
        """A background query finished."""

        def __init__(
            self,
            request: QueryRequest,
            series: sar.TimeSeries | None,
            error: str = "",
        ) -> None:
            super().__init__()
            self.request = request
            self.series = series
            self.error = error

    def __init__(
        self,
        *,
        initial_file: str | None = None,
        initial_start: str = "",
        initial_end: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._initial_file = initial_file
        self._initial_start = initial_start
        self._initial_end = initial_end
        self._archives: list[sar.LogFile] = []
        self._series: sar.TimeSeries | None = None
        self._metric: sar.MetricSpec = sar.METRICS[0]
        self._selected: list[str] = []
        self._available = False

    def compose(self) -> ComposeResult:
        self._archives = sar.list_log_files()
        options = [(f.label, str(f.path)) for f in self._archives]

        # An explicit --file may live outside the standard log directories, so
        # offer it as an option rather than rejecting it.
        explicit = str(Path(self._initial_file)) if self._initial_file else ""
        if explicit and all(value != explicit for _, value in options):
            options.insert(0, (f"{Path(explicit).name}  (custom)", explicit))

        self._available = bool(options) and shutil.which(sar.SADF_BINARY) is not None

        if not self._available:
            yield Static(self._unavailable_message(), id="history-unavailable")
            return

        with Horizontal(id="history-controls"):
            yield Label("Archive", classes="control-label")
            yield Select(
                options,
                value=explicit or options[0][1],
                allow_blank=False,
                id="archive-select",
            )
            yield Label("Metric", classes="control-label")
            yield Select(
                [(m.label, m.key) for m in sar.METRICS],
                value=sar.METRICS[0].key,
                allow_blank=False,
                id="metric-select",
            )
            yield Label("From", classes="control-label")
            yield Input(
                value=self._initial_start,
                placeholder="00:00:00",
                id="start-input",
                classes="time-input",
            )
            yield Label("To", classes="control-label")
            yield Input(
                value=self._initial_end,
                placeholder="23:59:59",
                id="end-input",
                classes="time-input",
            )
            yield Button("Reload", variant="primary", id="reload-button")

        with Horizontal(id="history-body"):
            yield SelectionList[str](id="series-select")
            yield PlotextPlot(id="history-plot")

        yield Static("", id="history-status")

    def _unavailable_message(self) -> str:
        return (
            "[b]Historical metrics unavailable[/b]\n\n"
            f"{sar.missing_reason()}\n\n"
            "[b]To enable on RHEL / Alma / Fedora:[/b]\n"
            "  sudo dnf install -y sysstat\n"
            "  sudo systemctl enable --now sysstat-collect.timer\n\n"
            "[b]To enable on Debian / Ubuntu:[/b]\n"
            "  sudo apt install -y sysstat\n"
            '  sudo sed -i "s/ENABLED=.*/ENABLED=\\"true\\"/" /etc/default/sysstat\n'
            "  sudo systemctl enable --now sysstat\n\n"
            "Live metrics on the other tabs are unaffected."
        )

    def _resolve_initial_file(self) -> str:
        """Honour an explicit --file, else default to the newest archive."""
        if self._initial_file:
            return str(Path(self._initial_file))
        return str(self._archives[0].path) if self._archives else ""

    def on_mount(self) -> None:
        if self._available:
            self.reload()

    # ---------------------------------------------------------------- events

    @on(Select.Changed, "#archive-select")
    @on(Select.Changed, "#metric-select")
    def _on_source_changed(self) -> None:
        # The series list belongs to the previous metric, so drop it and let
        # the new result pick its own defaults.
        self._selected = []
        self.reload()

    @on(Button.Pressed, "#reload-button")
    def _on_reload_pressed(self) -> None:
        sar.clear_cache()
        self.reload()

    @on(Input.Submitted, ".time-input")
    def _on_time_submitted(self) -> None:
        self.reload()

    @on(SelectionList.SelectedChanged, "#series-select")
    def _on_series_changed(self, event: SelectionList.SelectedChanged) -> None:
        self._selected = list(event.selection_list.selected)
        self._draw()

    # ----------------------------------------------------------------- query

    def _build_request(self) -> QueryRequest | None:
        """Validate the controls into a request, reporting the first problem."""
        start = normalise_time(self.query_one("#start-input", Input).value)
        if start is None:
            self._set_status("Invalid start time - expected HH:MM or HH:MM:SS.", error=True)
            return None

        end = normalise_time(self.query_one("#end-input", Input).value)
        if end is None:
            self._set_status("Invalid end time - expected HH:MM or HH:MM:SS.", error=True)
            return None

        if start and end and start >= end:
            self._set_status("Start time must be before end time.", error=True)
            return None

        archive = self.query_one("#archive-select", Select).value
        metric_key = self.query_one("#metric-select", Select).value
        metric = sar.METRICS_BY_KEY.get(str(metric_key), sar.METRICS[0])
        return QueryRequest(Path(str(archive)), metric, start, end)

    def reload(self) -> None:
        """Validate inputs and kick off a background query."""
        request = self._build_request()
        if request is None:
            return
        self._metric = request.metric
        self._set_status(f"Reading {request.metric.label} from {request.path.name}...")
        self._load(request)

    @work(thread=True, exclusive=True)
    def _load(self, request: QueryRequest) -> None:
        """Read the archive off the UI thread.

        sadf can take seconds on a full day of samples; blocking here would
        freeze the whole app.
        """
        try:
            series = sar.query(request.path, request.metric, request.start, request.end)
        except sar.SarError as exc:
            self.post_message(self.Loaded(request, None, str(exc)))
        else:
            self.post_message(self.Loaded(request, series))

    @on(Loaded)
    def _on_loaded(self, event: Loaded) -> None:
        # A slower earlier query can land after a newer one; ignore it.
        if event.request.metric.key != self._metric.key:
            return

        if event.error:
            self._series = None
            self._set_status(event.error, error=True)
            self._clear_plot(event.error)
            return

        series = event.series
        self._series = series
        selector = self.query_one("#series-select", SelectionList)

        if series is None or not series:
            selector.clear_options()
            self._set_status(f"No {event.request.metric.label} samples in this range.", error=True)
            self._clear_plot("No data in the selected range")
            return

        if not self._selected:
            self._selected = sar.choose_default_series(series, event.request.metric)

        with self.app.batch_update():
            selector.clear_options()
            for name in series.names:
                selector.add_option((name, name, name in self._selected))

        window = (
            f"{series.timestamps[0]:%H:%M:%S} to {series.timestamps[-1]:%H:%M:%S}"
            if series.timestamps
            else "no samples"
        )
        self._set_status(
            f"{len(series.timestamps)} samples ({window}) - "
            f"{len(series.columns)} series available on {series.nodename or 'host'}"
        )
        self._draw()

    # ---------------------------------------------------------------- render

    def _clear_plot(self, title: str) -> None:
        plot = self.query_one("#history-plot", PlotextPlot)
        plot.plt.clear_figure()
        plot.plt.title(title)
        plot.refresh()

    def _draw(self) -> None:
        """Render the selected series against a time axis."""
        series = self._series
        plot = self.query_one("#history-plot", PlotextPlot)
        plt = plot.plt
        plt.clear_figure()

        if series is None or not series:
            plt.title("No data")
            plot.refresh()
            return

        chosen = [name for name in self._selected if name in series.columns]
        if not chosen:
            plt.title("Select one or more series to plot")
            plot.refresh()
            return

        if len(chosen) > MAX_PLOTTED_SERIES:
            chosen = chosen[:MAX_PLOTTED_SERIES]

        for name in chosen:
            positions, values = series.indexed(name)
            if not values:
                continue
            # Plot against the sample position and label the axis manually:
            # plotext's own date handling round-trips through a naive UTC
            # conversion and shifts labels by the local UTC offset. Using
            # positions (not a fresh range) keeps sparse series - a device
            # that appeared late - aligned with the shared time axis.
            plt.plot(positions, values, label=name)

        self._apply_time_axis(plt, series.timestamps)

        unit = f" ({self._metric.unit})" if self._metric.unit else ""
        plt.title(f"{self._metric.label}{unit}")
        if self._metric.ylim is not None:
            plt.ylim(*self._metric.ylim)

        plot.refresh()

    @staticmethod
    def _apply_time_axis(plt, stamps: list[datetime], ticks: int = 5) -> None:
        """Label the x-axis with wall-clock times."""
        if not stamps:
            return
        count = len(stamps)
        step = max(1, (count - 1) // max(1, ticks - 1)) if count > 1 else 1
        positions = list(range(0, count, step))
        if positions[-1] != count - 1:
            positions.append(count - 1)

        spans_days = stamps[0].date() != stamps[-1].date()
        fmt = "%m-%d %H:%M" if spans_days else "%H:%M:%S"
        plt.xticks(positions, [stamps[i].strftime(fmt) for i in positions])

    def _set_status(self, message: str, *, error: bool = False) -> None:
        status = self.query_one("#history-status", Static)
        status.update(message)
        status.set_class(error, "-error")
