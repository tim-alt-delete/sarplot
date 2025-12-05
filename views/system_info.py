from textual.containers import Grid
from textual.widgets import Static
import platform
import psutil
import time

from utils.system import get_os_release_info, get_uptime

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

        system_info = get_os_release_info()
        release = system_info.get("PRETTY_NAME", "Unknown")
        kernel = platform.release()
        hostname = platform.node()
        uptime = get_uptime()

        self.os_block.update(
            f"Release: {release}\nKernel: {kernel}\nHostname: {hostname}\nUptime: {get_uptime()}"
        )

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