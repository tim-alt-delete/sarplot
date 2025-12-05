
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tabs, Tab
from textual.containers import Container, Grid, Vertical
from pathlib import Path

from views.system_info import SystemInfoView
from views.process_view import ProcessView
from views.cpu_plot import CPUPlotView

# An auxiliary function to create labels with border title and subtitle.
# def make_label_container(
#     text: str, id: str, border_title: str, border_subtitle: str
# ) -> Container:
#     lbl = Label(text, id=id)
#     lbl.border_title = border_title
#     lbl.border_subtitle = border_subtitle
#     return Container(lbl)

class SarPlot(App):
    """Textual app with tabs for system info and CPU plot."""

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
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
        self.notify("Exiting application...")
        self.exit()  # Properly quit the app
        
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
    SarPlot().run()

