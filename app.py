#!/usr/bin/env python

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane, Tab, Tabs
from textual.containers import Container, Grid, Vertical
from pathlib import Path

from views.system_info import SystemInfoView
from views.process_view import ProcessView
from views.cpu_plot import CPUPlotView

class SarPlot(App):
    """Textual app with tabs for system info and CPU plot."""
    COMMAND_PALETTE_BINDING = "p"
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
        ("l", "toggle_live_mode", "Toggle Live Data Mode")
    ]

    CSS_PATH = Path(__file__).parent / "styles" / "style.tcss"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("System Info", id="sys"):
                yield SystemInfoView(id="sysinfo")
            with TabPane("CPU", id="cpu"):
                yield CPUPlotView(id="cpuplot")
            with TabPane("Proc", id="procs"):
                yield ProcessView(id="procinfo")
        yield Footer()

    def on_mount(self) -> None:
        pass

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )

    def action_quit(self) -> None:
        """quits the application"""
        self.notify("Exiting application...")
        self.exit(return_code=0)

    def action_toggle_live_mode(self) -> None:
        cpuplot = self.query_one("#cpuplot", CPUPlotView)
        cpuplot.toggle_mode()

if __name__ == "__main__":
    app = SarPlot()
    app.run()
    import sys
    sys.exit(app.return_code or 0)

