
from textual.widgets import Label, Input, Button
from textual.containers import Horizontal, Vertical
from textual.app import ComposeResult
from textual_plotext import PlotextPlot
import psutil
from utils.cpu_stats import get_cpu_stats

class HistoricCPUPlotView(PlotextPlot):
    pass

class LiveCPUPlotView(PlotextPlot):
    pass

class CPUPlotView(PlotextPlot):
    """Displays CPU usage plot with toggle between live and historical data."""
    
    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Label("Start (YYYY-MM-DD HH:MM:SS)"),
                Input(placeholder="2025-12-04 08:00:00", id="start_input")               
            ),
            Horizontal(
                Label("End"),
                Input(placeholder="2025-12-04 10:30:00", id="end_input")
            ),
            Button("Apply Range", id="apply_btn")
        )
        yield HistoricCPUPlotView()


    def on_mount(self) -> None:
        self.mode = "live"  # Default mode
        self.cpu_history = []
        self.df = get_cpu_stats()  # Historical data
        self.set_interval(1.0, self.update_plot)  # Update every second

    def update_plot(self) -> None:
        plt = self.plt
        plt.clear_figure()

        # Collect live CPU usage
        cpu_percent = psutil.cpu_percent(interval=None)
        self.cpu_history.append(cpu_percent)
        if len(self.cpu_history) > 60:
            self.cpu_history.pop(0)

        if self.mode == "live":
            # Show live data
            plt.plot(self.cpu_history)
            plt.title("Live CPU Usage (%)")
        else:
            # Show historical data
            plt.plot(self.df['%busy'])
            plt.title("Historical CPU Usage (%)")

        plt.ylim(0, 100)
        self.refresh()

    def toggle_mode(self) -> None:
        """Switch between live and historical mode."""
        self.mode = "historic" if self.mode == "live" else "live"
        self.notify(f"Switched to {self.mode} mode")
