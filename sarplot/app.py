"""The sarplot application shell."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from sarplot.collectors import logs
from sarplot.views.history_view import HistoryView
from sarplot.views.live_view import LiveView
from sarplot.views.log_view import LogView
from sarplot.views.process_view import ProcessView
from sarplot.views.system_view import SystemInfoView

#: Tab id -> the view id it contains, used to pause off-screen timers.
TAB_VIEWS = {
    "tab-processes": "#processes",
    "tab-live": "#live",
    "tab-history": "#history",
    "tab-logs": "#logs",
    "tab-system": "#system",
}

DEFAULT_TAB = "tab-processes"


class SarPlot(App):
    """A terminal dashboard for live system metrics and sar history."""

    TITLE = "sarplot"
    CSS_PATH = Path(__file__).parent / "styles" / "sarplot.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("d", "toggle_theme", "Theme"),
        Binding("f5", "refresh_all", "Refresh"),
    ]

    def __init__(
        self,
        *,
        sa_file: str | None = None,
        start: str = "",
        end: str = "",
        refresh: float = 2.0,
        initial_tab: str = DEFAULT_TAB,
        log_file: str | None = None,
        log_dir: str = logs.DEFAULT_LOG_DIR,
        log_lines: int = 5000,
    ) -> None:
        super().__init__()
        self._sa_file = sa_file
        self._start = start
        self._end = end
        self._refresh = refresh
        self._initial_tab = initial_tab
        self._log_file = log_file
        self._log_dir = log_dir
        self._log_lines = log_lines

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial=self._initial_tab, id="tabs"):
            with TabPane("Processes", id="tab-processes"):
                yield ProcessView(id="processes", interval=self._refresh)
            with TabPane("Live", id="tab-live"):
                yield LiveView(id="live")
            with TabPane("History", id="tab-history"):
                yield HistoryView(
                    id="history",
                    initial_file=self._sa_file,
                    initial_start=self._start,
                    initial_end=self._end,
                )
            with TabPane("Logs", id="tab-logs"):
                yield LogView(
                    id="logs",
                    log_file=self._log_file,
                    log_dir=self._log_dir,
                    max_lines=self._log_lines,
                )
            with TabPane("System", id="tab-system"):
                yield SystemInfoView(id="system")
        yield Footer()

    def on_mount(self) -> None:
        # Every view mounts at once, so pause the ones that start hidden
        # rather than letting four timers poll in the background.
        self._sync_timers(self._initial_tab)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._sync_timers(event.pane.id)

    def _sync_timers(self, active_tab: str | None) -> None:
        """Run only the active tab's polling timer."""
        for tab_id, selector in TAB_VIEWS.items():
            try:
                view = self.query_one(selector)
            except Exception:
                continue
            resume = getattr(view, "resume", None)
            pause = getattr(view, "pause", None)
            if tab_id == active_tab:
                if resume is not None:
                    resume()
            elif pause is not None:
                pause()

    def action_toggle_theme(self) -> None:
        """Flip between the light and dark variants."""
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"

    def action_refresh_all(self) -> None:
        """Force the active view to re-read its data."""
        active = self.query_one("#tabs", TabbedContent).active
        selector = TAB_VIEWS.get(active)
        if selector is None:
            return
        view = self.query_one(selector)
        for method in ("refresh_processes", "reload", "reload_log", "refresh_info"):
            action = getattr(view, method, None)
            if action is not None:
                action()
                self.notify("Refreshed.")
                return
