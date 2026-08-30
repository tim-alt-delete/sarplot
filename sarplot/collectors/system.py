"""Host, OS and hardware facts."""

from __future__ import annotations

import os
import platform
import socket
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from sarplot.formatting import format_uptime

OS_RELEASE_PATHS = ("/etc/os-release", "/usr/lib/os-release")


@dataclass(frozen=True)
class DiskUsage:
    """Usage for one mounted filesystem."""

    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int
    percent: float


@dataclass(frozen=True)
class Interface:
    """A network interface and its addresses."""

    name: str
    ipv4: tuple[str, ...]
    ipv6: tuple[str, ...]
    is_up: bool
    speed_mbps: int


def get_os_release() -> dict[str, str]:
    """Parse ``/etc/os-release`` into a dict.

    Returns an empty dict on platforms that do not provide it, so callers can
    fall back to `platform` without special-casing.
    """
    for candidate in OS_RELEASE_PATHS:
        path = Path(candidate)
        if not path.is_file():
            continue
        info: dict[str, str] = {}
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                info[key.strip()] = value.strip().strip('"').strip("'")
        except OSError:
            continue
        return info
    return {}


def get_distribution() -> str:
    """A human-readable OS name."""
    release = get_os_release()
    return (
        release.get("PRETTY_NAME")
        or release.get("NAME")
        or f"{platform.system()} {platform.release()}".strip()
        or "Unknown"
    )


def get_cpu_model() -> str:
    """Best-effort CPU model name.

    `platform.processor()` returns an empty string on virtually every Linux
    build, so read /proc/cpuinfo first and only then fall back.
    """
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        try:
            for line in cpuinfo.read_text(errors="replace").splitlines():
                key, _, value = line.partition(":")
                # x86 uses "model name"; several ARM builds only expose
                # "Hardware" or "Model".
                if key.strip() in ("model name", "Model", "Hardware", "cpu model"):
                    model = value.strip()
                    if model:
                        return model
        except OSError:
            pass
    return platform.processor() or platform.machine() or "Unknown CPU"


def get_uptime_seconds() -> float:
    return max(0.0, time.time() - psutil.boot_time())


def get_uptime() -> str:
    """Uptime formatted as ``NNd NNh NNm``."""
    return format_uptime(get_uptime_seconds())


def get_boot_time() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(psutil.boot_time()))


def get_load_avg() -> tuple[float, float, float]:
    """1, 5 and 15 minute load averages."""
    try:
        one, five, fifteen = psutil.getloadavg()
    except (AttributeError, OSError):
        return 0.0, 0.0, 0.0
    return one, five, fifteen


def get_cpu_counts() -> tuple[int, int]:
    """Physical and logical core counts.

    Physical count is unavailable in some containers and VMs; it falls back to
    the logical count rather than None.
    """
    logical = psutil.cpu_count(logical=True) or 0
    physical = psutil.cpu_count(logical=False) or logical
    return physical, logical


def get_disks() -> list[DiskUsage]:
    """Usage for every mounted physical filesystem."""
    disks: list[DiskUsage] = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except (PermissionError, OSError):
            # Unreadable mounts (permissions, disconnected network shares)
            # are expected; skip them rather than failing the whole table.
            continue
        disks.append(
            DiskUsage(
                device=partition.device,
                mountpoint=partition.mountpoint,
                fstype=partition.fstype,
                total=usage.total,
                used=usage.used,
                free=usage.free,
                percent=usage.percent,
            )
        )
    return disks


def get_interfaces() -> list[Interface]:
    """Network interfaces with their IPv4 and IPv6 addresses."""
    stats = psutil.net_if_stats()
    interfaces: list[Interface] = []

    for name, addresses in psutil.net_if_addrs().items():
        ipv4 = tuple(a.address for a in addresses if a.family == socket.AF_INET)
        # Link-local IPv6 carries a %scope suffix that adds noise.
        ipv6 = tuple(
            a.address.partition("%")[0]
            for a in addresses
            if a.family == socket.AF_INET6
        )
        if not ipv4 and not ipv6:
            continue

        stat = stats.get(name)
        interfaces.append(
            Interface(
                name=name,
                ipv4=ipv4,
                ipv6=ipv6,
                is_up=bool(stat.isup) if stat else False,
                speed_mbps=int(stat.speed) if stat else 0,
            )
        )

    interfaces.sort(key=lambda i: (not i.is_up, i.name))
    return interfaces


def get_hostname() -> str:
    return platform.node() or socket.gethostname() or "unknown"


def get_kernel() -> str:
    return f"{platform.system()} {platform.release()}".strip()


def is_root() -> bool:
    """Whether the app is running with full signalling privileges."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False
