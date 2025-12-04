from textual_plotext import PlotextPlot
import psutil
from utils.cpu_stats import get_cpu_stats

# TODO: Allow plotting of either historical data, and live data

# class CPUPlotView(PlotextPlot):
#     """Displays live CPU usage plot."""

#     def on_mount(self) -> None:
#         self.set_interval(1.0, self.update_plot)  # Update every second
#         self.cpu_history = []

#     def update_plot(self) -> None:
#         # Get current CPU usage
#         cpu_percent = psutil.cpu_percent(interval=None)
#         self.cpu_history.append(cpu_percent)

#         # Keep last 60 points
#         if len(self.cpu_history) > 60:
#             self.cpu_history.pop(0)

#         # Update plot
#         plt = self.plt
#         plt.clear_figure()
#         plt.plot(self.cpu_history)
#         plt.title("CPU Usage (%)")
#         plt.ylim(0, 100)
#         self.refresh()


class CPUPlotView(PlotextPlot):
    """Displays historical CPU usage plot."""

    def on_mount(self) -> None:
        self.df = get_cpu_stats()
        self.update_plot()

    def update_plot(self) -> None:
        # Update plot
        plt = self.plt
        plt.clear_figure()
        plt.plot(self.df['%busy'])
        plt.title("CPU Usage (%)")
        plt.ylim(0, 100)
        self.refresh()