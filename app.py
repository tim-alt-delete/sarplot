#!/usr/bin/env python

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane

from views.system_info import SystemInfoView
from views.process_view import ProcessView
from views.cpu_plot import CPUPlotView
import sys


class SarPlot(App):
    """Textual app with tabs for system info and CPU plot."""
    COMMAND_PALETTE_BINDING = "p"
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
    ]

    CSS_PATH = Path(__file__).parent / "styles" / "test2.tcss"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        tc = TabbedContent()
        with tc:
            tp = TabPane("System Info", id="systab")
            with tp:
                yield SystemInfoView(id="sysinfo")
            with TabPane("CPU", id="cputab"):
                yield CPUPlotView(id="cpuplot")
            with TabPane("Proc", id="procstab"):
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

if __name__ == "__main__":
    app = SarPlot()
    app.run()
    import sys
    sys.exit(app.return_code or 0)

