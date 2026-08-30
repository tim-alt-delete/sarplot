from textual.containers import Grid
from textual.widgets import DataTable
import platform
from utils.system import get_kernel_version
import psutil

from utils.system import get_uptime


class SystemInfoView(Grid):

    def on_mount(self) -> None:

        # Layout
        self.styles.grid_template_columns = "1fr 1fr"
        self.styles.grid_gap = 1
        self.styles.padding = 1

        self.os_table = DataTable()
        self.os_table.zebra_stripes = True
        self.os_table.cursor_type = "row"
        self.os_table.border_title = "OS Info"
        self.os_table.add_columns(
            "Property",
            "Value",
        )

        self.cpu_table = DataTable()
        self.cpu_table.zebra_stripes = True
        self.cpu_table.cursor_type = "row"
        self.cpu_table.border_title = "CPU & Memory"
        self.cpu_table.add_columns(
            "Property",
            "Value",
        )

        self.disk_table = DataTable()
        self.disk_table.zebra_stripes = True
        self.disk_table.cursor_type = "row"
        self.disk_table.border_title = "Disks"
        self.disk_table.add_columns(
            "Filesystem",
            "1K-blocks",
            "Used",
            "Available",
            "Use%",
            "Mounted on",
        )

        self.net_table = DataTable()
        self.net_table.zebra_stripes = True
        self.net_table.cursor_type = "row"
        self.net_table.border_title = "Network Interfaces"
        self.net_table.add_columns(
            "Interface",
            "IP Address",
        )

        # Mount widgets
        self.mount(self.os_table)
        self.mount(self.cpu_table)
        self.mount(self.disk_table)
        self.mount(self.net_table)

        # Refresh every 60 seconds
        self.set_interval(60.0, self.refresh_info)
        self.refresh_info()

    def refresh_info(self) -> None:
        # ================= OS INFO =================
        self.os_table.clear()

        # system_info = get_os_release_info()

        kernel_info = get_kernel_version()

        # self.os_table.add_row(
        #     "Release",
        #     system_info.get("PRETTY_NAME", "Unknown"),
        # )

        self.os_table.add_row(
            "Kernel",
            platform.release(),
        )

        self.os_table.add_row(
            "Hostname",
            platform.node(),
        )

        self.os_table.add_row(
            "Uptime",
            get_uptime(),
        )

        # ================= CPU & MEMORY =================
        self.cpu_table.clear()
        cpu_cores = psutil.cpu_count(logical=True)
        memory = round(
            psutil.virtual_memory().total / (1024 ** 3),
            2,
        )
        self.cpu_table.add_row(
            "CPU Cores",
            str(cpu_cores),
        )
        self.cpu_table.add_row(
            "Memory",
            f"{memory} GB",
        )

        # ================= DISKS =================
        self.disk_table.clear()

        for fs in psutil.disk_partitions(all=False):

            try:
                usage = psutil.disk_usage(fs.mountpoint)

                self.disk_table.add_row(
                    fs.device,
                    str(int(usage.total / 1024)),
                    str(int(usage.used / 1024)),
                    str(int(usage.free / 1024)),
                    f"{usage.percent}%",
                    fs.mountpoint,
                )

            except Exception:
                continue

        # ================= NETWORK =================

        self.net_table.clear()

        for iface, addrs in psutil.net_if_addrs().items():

            ips = [
                a.address
                for a in addrs
                if a.family == 2
            ]

            if ips:

                self.net_table.add_row(
                    iface,
                    ", ".join(ips),
                )