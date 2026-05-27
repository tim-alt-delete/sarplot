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
        filesystems = []
        for fs in psutil.disk_partitions(all=False):
            try:
                device = fs.device
                mountpoint = fs.mountpoint
                fstype = fs.fstype

                usage = psutil.disk_usage(fs.mountpoint)
                size_KB = usage.total / 1024
                used_KB = usage.used / 1024
                free_KB = usage.free / 1024
                percent_used = usage.percent

                fs_info = {
                    "device": device,
                    "mountpoint": mountpoint,
                    "fstype": fstype,
                    "size_KB": size_KB,
                    "used_KB": used_KB,
                    "free_KB": free_KB,
                    "percent_used": percent_used,
                }
                filesystems.append(fs_info)
            except PermissionError:
                continue

            header = (
                f"{'Filesystem':<20}"
                f"{'1K-blocks':>12}"
                f"{'Used':>12}"
                f"{'Available':>12}"
                f"{'Use%':>8}   "
                f"{'Mounted on':<20}\n"
            )
            info_text = header

            for d in filesystems:
                info_text += (
                    f"{d['device']:<20}"
                    f"{d['size_KB']:>12}"
                    f"{d['used_KB']:>12}"
                    f"{d['free_KB']:>12}"
                    f"{d['percent_used']:>7}%   "
                    f"{d['mountpoint']}\n"
            )
        self.disk_block.update(info_text)

        # Network Interfaces
        net_info = []
        for iface, addrs in psutil.net_if_addrs().items():
            ips = [a.address for a in addrs if a.family == 2]  # AF_INET
            if ips:
                net_info.append(f"{iface}: {', '.join(ips)}")
        self.net_block.update("\n".join(net_info) if net_info else "No interfaces")