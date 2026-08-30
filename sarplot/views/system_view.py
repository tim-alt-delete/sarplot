"""A static overview of the host: OS, hardware, filesystems and network."""

from __future__ import annotations

import psutil
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.widgets import DataTable, Static

from sarplot.collectors import system
from sarplot.formatting import format_bytes

#: Host facts change rarely; usage does, but not fast enough to poll hard.
REFRESH_SECONDS = 15.0


class SystemInfoView(Grid):
    """Four panels of host information, refreshed on a slow timer."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._timer = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="host-panel", classes="info-panel"):
            yield Static(id="host-info")
        with VerticalScroll(id="resource-panel", classes="info-panel"):
            yield Static(id="resource-info")
        with VerticalScroll(id="disk-panel", classes="info-panel"):
            yield DataTable(id="disk-table")
        with VerticalScroll(id="net-panel", classes="info-panel"):
            yield DataTable(id="net-table")

    def on_mount(self) -> None:
        self.query_one("#host-panel").border_title = "Host"
        self.query_one("#resource-panel").border_title = "CPU & Memory"
        self.query_one("#disk-panel").border_title = "Filesystems"
        self.query_one("#net-panel").border_title = "Network"

        disks = self.query_one("#disk-table", DataTable)
        disks.add_columns("Filesystem", "Type", "Size", "Used", "Avail", "Use%", "Mounted on")
        disks.zebra_stripes = True
        disks.cursor_type = "row"

        net = self.query_one("#net-table", DataTable)
        net.add_columns("Interface", "State", "Speed", "IPv4", "IPv6")
        net.zebra_stripes = True
        net.cursor_type = "row"

        self._timer = self.set_interval(REFRESH_SECONDS, self.refresh_info)
        self.refresh_info()

    def pause(self) -> None:
        """Stop refreshing while the tab is hidden."""
        if self._timer is not None:
            self._timer.pause()

    def resume(self) -> None:
        if self._timer is not None:
            self._timer.resume()
            self.refresh_info()

    def refresh_info(self) -> None:
        self._render_host()
        self._render_resources()
        self._render_disks()
        self._render_network()

    def _render_host(self) -> None:
        rows = [
            ("Hostname", system.get_hostname()),
            ("OS", system.get_distribution()),
            ("Kernel", system.get_kernel()),
            ("Architecture", psutil.os.uname().machine if hasattr(psutil.os, "uname") else ""),
            ("Uptime", system.get_uptime()),
            ("Booted", system.get_boot_time()),
            ("Privileges", "root" if system.is_root() else "unprivileged"),
        ]
        self.query_one("#host-info", Static).update(_definition_list(rows))

    def _render_resources(self) -> None:
        physical, logical = system.get_cpu_counts()
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        one, five, fifteen = system.get_load_avg()

        frequency = ""
        try:
            current = psutil.cpu_freq()
            if current and current.current:
                frequency = f"{current.current / 1000:.2f} GHz"
        except (NotImplementedError, AttributeError, OSError):
            # cpu_freq is unavailable in many containers and on Apple silicon.
            frequency = ""

        rows = [
            ("Model", system.get_cpu_model()),
            ("Cores", f"{physical} physical / {logical} logical"),
        ]
        if frequency:
            rows.append(("Frequency", frequency))
        rows += [
            ("Load average", f"{one:.2f}  {five:.2f}  {fifteen:.2f}"),
            (
                "Memory",
                f"{format_bytes(memory.used)} used of {format_bytes(memory.total)} "
                f"({memory.percent:.1f}%)",
            ),
            ("Available", format_bytes(memory.available)),
            (
                "Swap",
                f"{format_bytes(swap.used)} used of {format_bytes(swap.total)} "
                f"({swap.percent:.1f}%)"
                if swap.total
                else "none configured",
            ),
        ]
        self.query_one("#resource-info", Static).update(_definition_list(rows))

    def _render_disks(self) -> None:
        table = self.query_one("#disk-table", DataTable)
        table.clear()
        for disk in system.get_disks():
            table.add_row(
                disk.device,
                disk.fstype,
                Text(format_bytes(disk.total), justify="right"),
                Text(format_bytes(disk.used), justify="right"),
                Text(format_bytes(disk.free), justify="right"),
                Text(f"{disk.percent:.0f}%", justify="right"),
                disk.mountpoint,
            )

    def _render_network(self) -> None:
        table = self.query_one("#net-table", DataTable)
        table.clear()
        for interface in system.get_interfaces():
            table.add_row(
                interface.name,
                "up" if interface.is_up else "down",
                f"{interface.speed_mbps} Mb/s" if interface.speed_mbps else "-",
                ", ".join(interface.ipv4) or "-",
                ", ".join(interface.ipv6) or "-",
            )


def _definition_list(rows: list[tuple[str, str]]) -> str:
    """Render label/value pairs with the labels aligned."""
    width = max((len(label) for label, _ in rows), default=0)
    return "\n".join(f"[dim]{label:<{width}}[/dim]  {value}" for label, value in rows)
