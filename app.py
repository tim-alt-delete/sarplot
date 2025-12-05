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
        yield Tabs(Tab("System Info", id="sys"), Tab("CPU", id="cpu"), Tab("Procs", id="procs"))
        yield SystemInfoView(id="sysinfo")
        yield ProcessView(id="procinfo")
        yield CPUPlotView(id="cpuplot")
        yield Footer()

    def on_mount(self) -> None:
        # Initially show System Info and hide CPU plot
        self.query_one("#sysinfo").display = True
        self.query_one("#cpuplot").display = False
        self.query_one("#procinfo").display = False

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
        
    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        sysinfo = self.query_one("#sysinfo")
        cpuplot = self.query_one("#cpuplot")
        procinfo = self.query_one("#procinfo")

        if event.tab.id == "sys":
            sysinfo.display = True
            cpuplot.display = False
            procinfo.display = False
        elif event.tab.id == "cpu":
            sysinfo.display = False
            cpuplot.display = True
            procinfo.display = False
        elif event.tab.id == "procs":
            sysinfo.display = False
            cpuplot.display = False
            procinfo.display = True

if __name__ == "__main__":
    app = SarPlot()
    app.run()
    import sys
    sys.exit(app.return_code or 0)

