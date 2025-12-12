
from textual.containers import Grid, Container, VerticalScroll, Horizontal
from textual.widgets import Static
from textual.events import Resize
from textual.app import ComposeResult
from textual_plotext import PlotextPlot

import platform
import psutil
import subprocess

from utils.system import get_os_release_info, get_uptime
from utils.cpu_stats import get_cpu_stats


class SystemInfoView(Container):
    """Displays system information in a grid layout with borders and live refresh."""

    host_info_static: Static
    cpu_block: Static
    disk_block: Static
    net_block: Static

    SMALL_BREAKPOINT = 80

    # def compose(self) -> ComposeResult:
    #     # Define the structure and yield all top-level elements
    #     yield Container(
    #         Static(id="host-info-static"),
    #         id="host-info-container"
    #     )
    #     yield Container(
    #         Static(id="cpu-info-static"),
    #         Sparkline(data=[1,2,3,4,5,4,3,2,1], id="cpu-sparkline"),
    #         id="cpu-info-container"
    #     )
    #     yield Static(id="disk-info-static")
    #     yield Static(id="net-info-static")

    def compose(self) -> ComposeResult:
        yield Grid(
            VerticalScroll(
                Static(id="host-info"),
                Static(id="cpu-info"),
                id="system-overview"
            ),
            VerticalScroll(
                Horizontal(
                    PlotextPlot(id="plot_cpu"),
                ),
                Horizontal(
                    PlotextPlot(id="plot_cpu"),
                )
            )
        )
        # with Grid(id="sys-grid"):
        #     with Container(id="host-info-container"):
        #         yield Static(id="host-info-static")

        #     with Container(id="cpu-info-container"):
        #         yield Static("CPU", id="cpu-info-static")
        #         yield Sparkline(id="cpu-sparkline")

        #     yield Static(id="disk-info-static")
        #     yield Static(id="net-info-static")
        # g = Grid(id="test-grid")
        # with g:
        #     c1 = VerticalScroll (id="c1", can_focus=True)
        #     c1.border_title = "c1"
        #     with c1:
        #         yield Static(text)
        #         yield Sparkline(data=[1,2,3,4,5,4,3,2,1])
        #     c2 = VerticalScroll (id="c2", can_focus=True)
        #     c2.border_title = "c2"
        #     with c2:
        #         yield Static(text)
        #         yield Sparkline(data=[1,2,3,4,5,4,3,2,1])
        #     c3 = VerticalScroll (id="c3", can_focus=True)
        #     c3.border_title = "c3"
        #     with c3:
        #         yield Static(text)
        #     c4 = VerticalScroll (id="c4", can_focus=True)
        #     c4.border_title = "c4"
        #     with c4:
        #         yield Static(text)

    def on_mount(self) -> None:
        self.host_info = self.query_one("#host-info")
        self.host_info.border_title = "Host Info"

        self.cpu_info = self.query_one("#cpu-info")
        self.cpu_info.border_title = "CPU"
        # self.host_info_container = self.query_one("#host-info-container")
        # self.host_info_container.border_title = "Host Info"

        # self.cpu_info_container = self.query_one("#cpu-info-container")
        # self.cpu_info_container.border_title = "CPU"

        # self.cpu_info_static = self.query_one("#cpu-info-static")
        # # self.cpu_info_static.border_title = "CPU & Memory"

        # self.disk_info_static = self.query_one("#disk-info-static")
        # self.disk_info_static.border_title = "Disks"

        # self.net_info_static = self.query_one("#net-info-static")
        # self.net_info_static.border_title = "Network"

        # Add blocks to grid
        # self.mount(self.host_info_container)
        # self.mount(self.cpu_block)
        # self.mount(self.disk_block)
        # self.mount(self.net_block)

        self.system_overview = self.query_one("#system-overview")

        # Refresh every 5 seconds
        self.set_interval(5.0, self.refresh_info)
        self.refresh_info()
        self.cpu_history = []
        self.df = get_cpu_stats()  # Historical data
        self.set_interval(1.0, self.update_plot)  # Update every second

    def refresh_info(self) -> None:
        system_info = get_os_release_info()
        release = system_info.get("PRETTY_NAME", "Unknown")
        kernel = platform.release()
        hostname = platform.node()
        uptime = get_uptime()

        self.host_info.update(
            f"Release: {release}\nKernel: {kernel}\nHostname: {hostname}\nUptime: {get_uptime()}"
        )

        # CPU & Memory
        cpu_cores = psutil.cpu_count(logical=True)
        command = 'lscpu | grep -i "model name" | awk -F \':\' "{print \$2}"'

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            cpu_model_name = result.stdout.strip()
            print(f"CPU Model Name: {cpu_model_name}")

        except subprocess.CalledProcessError as e:
            print(f"Command failed. Stderr: {e.stderr}")
        except FileNotFoundError:
            print("The required shell or command was not found.")
        # memory = f"{round(psutil.virtual_memory().total/(1024**3),2)} GB"
        self.cpu_info.update(f"Model name: {cpu_model_name}\nCores: {cpu_cores}")

        # # Disks
        # disk_info = get_disk_info()
        # self.disk_info_static.update("\n".join(disk_info) if disk_info else "No disks found")

        # net_info = get_network_interfaces()
        # self.net_info_static.update("\n".join(net_info) if net_info else "No interfaces")

    def update_plot(self) -> None:
        plt = self.query_one("#plot_cpu", PlotextPlot).plt
        plt.clear_figure()

        # Collect live CPU usage
        cpu_percent = psutil.cpu_percent(interval=None)
        self.cpu_history.append(cpu_percent)
        if len(self.cpu_history) > 60:
            self.cpu_history.pop(0)

        # Show live data
        plt.plot(self.cpu_history)
        plt.title("Live CPU Usage (%)")

        plt.ylim(0, 100)
        self.query_one("#plot_cpu", PlotextPlot).refresh()

    def on_resize(self, event: Resize) -> None:
        width = event.size[0]
        if width <= self.SMALL_BREAKPOINT: 
            self.system_overview.styles.display = "none"
        else:
            self.system_overview.styles.display = "block"