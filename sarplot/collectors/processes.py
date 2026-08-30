"""Process enumeration via psutil."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psutil

#: psutil status -> the single-letter code `top`/`htop` display.
#: Keyed on psutil's literal status strings rather than its STATUS_* constants,
#: which vary between releases (STATUS_WAKE_KILL was dropped in psutil 7).
PROC_STATES: dict[str, str] = {
    "running": "R",
    "sleeping": "S",
    "disk-sleep": "D",
    "stopped": "T",
    "tracing-stop": "t",
    "zombie": "Z",
    "dead": "X",
    "wake-kill": "K",
    "waking": "W",
    "parked": "P",
    "idle": "I",
    "locked": "L",
    "waiting": "W",
    "suspended": "V",
}

#: Command lines can run to kilobytes; keep the column bounded.
COMMAND_LIMIT = 240


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    """A snapshot of one process.

    Values are kept numeric so the table can sort on them; formatting happens
    at render time.
    """

    pid: int
    username: str
    nice: int
    vms: int
    rss: int
    shared: int
    status: str
    cpu_percent: float
    mem_percent: float
    cpu_time: float
    command: str
    name: str

    @property
    def is_zombie(self) -> bool:
        return self.status == "Z"


def _read_process(proc: psutil.Process) -> ProcessInfo | None:
    """Build a ProcessInfo, or None if the process is inaccessible."""
    try:
        with proc.oneshot():
            memory = proc.memory_info()
            times = proc.cpu_times()

            try:
                command = " ".join(proc.cmdline()) or proc.name()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                # Kernel threads and protected processes hide their argv.
                command = proc.name()

            return ProcessInfo(
                pid=proc.pid,
                username=_safe_username(proc),
                nice=int(proc.nice()),
                vms=memory.vms,
                rss=memory.rss,
                # `shared` is Linux-only; absent on macOS and some BSDs.
                shared=getattr(memory, "shared", 0),
                status=PROC_STATES.get(proc.status(), "?"),
                cpu_percent=proc.cpu_percent(),
                mem_percent=proc.memory_percent(),
                cpu_time=times.user + times.system,
                command=command[:COMMAND_LIMIT],
                name=proc.name(),
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None
    except OSError:
        # /proc entries can vanish mid-read on a busy system.
        return None


def _safe_username(proc: psutil.Process) -> str:
    """Resolve the owner, falling back to a uid when NSS lookup fails."""
    try:
        return proc.username()
    except (psutil.AccessDenied, KeyError):
        try:
            return str(proc.uids().real)
        except (psutil.Error, AttributeError):
            return "?"


def get_processes() -> list[ProcessInfo]:
    """Snapshot every process the current user can see.

    Processes that disappear or deny access mid-iteration are skipped, which
    is normal on a busy system and not an error.
    """
    processes: list[ProcessInfo] = []
    for proc in psutil.process_iter():
        info = _read_process(proc)
        if info is not None:
            processes.append(info)
    return processes


def terminate(pid: int, *, force: bool = False) -> None:
    """Send SIGTERM, or SIGKILL when ``force`` is set.

    Raises:
        psutil.NoSuchProcess: the process already exited.
        psutil.AccessDenied: insufficient privileges.
    """
    proc = psutil.Process(pid)
    if force:
        proc.kill()
    else:
        proc.terminate()


def set_nice(pid: int, nice: int) -> int:
    """Set a process's nice value, clamped to the valid range.

    Returns the value actually applied.

    Raises:
        psutil.NoSuchProcess: the process already exited.
        psutil.AccessDenied: lowering niceness requires privileges.
    """
    nice = max(-20, min(19, nice))
    psutil.Process(pid).nice(nice)
    return nice


def can_signal(pid: int) -> bool:
    """Whether the current user can plausibly signal this process.

    A cheap pre-flight check so the UI can warn before prompting; root can
    signal anything, otherwise the uids must match.
    """
    if os.geteuid() == 0:
        return True
    try:
        return psutil.Process(pid).uids().real == os.getuid()
    except (psutil.Error, AttributeError):
        return False
