
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tabs, Tab, Static, Label
from textual.containers import Container, Grid, Vertical
from textual_plotext import PlotextPlot
import platform
import psutil
import time

from textual.widgets import DataTable, Input
class ProcessView(Vertical):
    def compose(self):
        yield Input(placeholder="Search process...", id="search")
        yield DataTable(id="proc_table")

    def on_mount(self):
        self.table = self.query_one("#proc_table", DataTable)
        self.table.add_columns("PID", "Name", "CPU %", "Memory MB")
        self.set_interval(2.0, self.refresh_processes)
        self.processes = []  # Store all processes for filtering

    def refresh_processes(self):
        self.processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
            mem_mb = round(proc.info['memory_info'].rss / (1024**2), 2)
            self.processes.append((str(proc.info['pid']), proc.info['name'], str(proc.info['cpu_percent']), str(mem_mb)))
        self.apply_filter()

    def on_input_changed(self, event: Input.Changed):
        self.apply_filter(event.value)


    def apply_filter(self, query=""):
        self.table.clear()
        query = query.strip().lower()
        for row in self.processes:
            pid, name, cpu, mem = row
            if query == "" or query in name.lower() or query in pid:
                self.table.add_row(pid, name, cpu, mem)


def get_os_release_info():
    info = {}
    with open("/etc/os-release") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                info[key] = value.strip('"')
    return info

# os_info = get_os_release_info()
# print(os_info["PRETTY_NAME"])  # e.g., Ubuntu 22.04.3 LTS


# An auxiliary function to create labels with border title and subtitle.
def make_label_container(
    text: str, id: str, border_title: str, border_subtitle: str
) -> Container:
    lbl = Label(text, id=id)
    lbl.border_title = border_title
    lbl.border_subtitle = border_subtitle
    return Container(lbl)

# -------------------------------
# Widget for System Info Tab
# -------------------------------
class SystemInfoView(Grid):
    """Displays system information in a grid layout with borders and live refresh."""

    def on_mount(self) -> None:
        # Configure grid layout: 2 columns, auto rows
        self.styles.grid_template_columns = "1fr 1fr"
        self.styles.grid_gap = 1
        self.styles.padding = 1

        # Create blocks
        self.os_block = Static()
        self.os_block.border_title = "OS Info"

        self.cpu_block = Static()
        self.cpu_block.border_title = "CPU & Memory"

        self.disk_block = Static()
        self.disk_block.border_title = "Disks"

        self.net_block = Static()
        self.net_block.border_title = "Network Interfaces"

        # Add blocks to grid
        self.mount(self.os_block)
        self.mount(self.cpu_block)
        self.mount(self.disk_block)
        self.mount(self.net_block)

        # Refresh every 5 seconds
        self.set_interval(5.0, self.refresh_info)
        self.refresh_info()

    def refresh_info(self) -> None:
        # OS Info
        system = platform.system()
        kernel = platform.release()
        hostname = platform.node()
        uptime_seconds = time.time() - psutil.boot_time()
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        uptime = f"{days}d {hours}h {minutes}m"
        self.os_block.update(f"System: {system}\nKernel: {kernel}\nHostname: {hostname}\nUptime: {uptime}")

        # CPU & Memory
        cpu_cores = psutil.cpu_count(logical=True)
        memory = f"{round(psutil.virtual_memory().total/(1024**3),2)} GB"
        self.cpu_block.update(f"Cores: {cpu_cores}\nMemory: {memory}")

        # Disks
        disk_info = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_info.append(f"{part.device}: {round(usage.total/(1024**3),2)} GB total")
            except PermissionError:
                continue
        self.disk_block.update("\n".join(disk_info) if disk_info else "No disks found")

        # Network Interfaces
        net_info = []
        for iface, addrs in psutil.net_if_addrs().items():
            ips = [a.address for a in addrs if a.family == 2]  # AF_INET
            if ips:
                net_info.append(f"{iface}: {', '.join(ips)}")
        self.net_block.update("\n".join(net_info) if net_info else "No interfaces")


# -------------------------------
# Widget for CPU Plot Tab
# -------------------------------
class CPUPlotView(PlotextPlot):
    """Displays live CPU usage plot."""

    def on_mount(self) -> None:
        self.set_interval(1.0, self.update_plot)  # Update every second
        self.cpu_history = []

    def update_plot(self) -> None:
        # Get current CPU usage
        cpu_percent = psutil.cpu_percent(interval=None)
        self.cpu_history.append(cpu_percent)

        # Keep last 50 points
        if len(self.cpu_history) > 50:
            self.cpu_history.pop(0)

        # Update plot
        plt = self.plt
        plt.clear_figure()
        plt.plot(self.cpu_history)
        plt.title("CPU Usage (%)")
        plt.ylim(0, 100)
        self.refresh()


# -------------------------------
# Main Application
# -------------------------------
class SarPlot(App):
    """Textual app with tabs for system info and CPU plot."""

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
        ]

    CSS_PATH = "style.tcss"

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

