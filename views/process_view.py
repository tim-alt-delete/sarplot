from textual.containers import Vertical
from textual.widgets import DataTable, Input, Static
from utils.system import get_uptime
import psutil

PROC_STATES = {
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
}

def format_bytes(num):
    for unit in ["B", "K", "M", "G", "T"]:
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024

class ProcessView(Vertical):
    def compose(self):
        yield Static(get_uptime(), id="proc_stats")
        yield Input(placeholder="Search process...", id="search")
        yield DataTable(id="proc_table")

    def on_mount(self):
        self.table = self.query_one("#proc_table", DataTable)
        self.table.zebra_stripes = True
        self.table.cursor_type = "row"
        self.search = self.query_one("#search", Input)
        self.table.add_columns("PID", "USER", "NI", "VIRT", "RES", "SHR", "S", "CPU%", "MEM%", "TIME+", "Command")
        self.set_interval(2.0, self.refresh_processes)
        self.processes = []  # Store all processes for filtering

    def refresh_processes(self):
        self.processes = []

        for proc in psutil.process_iter():
            try:
                pid = proc.pid
                username = proc.username()
                #priority = proc.
                nice = proc.nice()

                mem_info = proc.memory_info()
                # virtual memory
                vms = format_bytes(mem_info.vms)
                # resident set size
                rss = format_bytes(mem_info.rss)
                # shared memory
                # Does not exist on all platforms, notably macOS, and some BSD systems
                shared = getattr(mem_info, "shared", "?")
                status = PROC_STATES.get(proc.status(), "?")
                cpu_percent = proc.cpu_percent()
                mem_percent = proc.memory_percent()
                time = proc.cpu_times().user + proc.cpu_times().system # minutes
                if proc.cmdline():
                    command = " ".join(proc.cmdline())
                else:
                    command = proc.name()
                # prevent very long command lines
                command = command[:120]
                proc_info = {
                    "pid": pid,
                    "username": username,
                    "nice": nice,
                    "vms": vms,
                    "rss": rss,
                    "shared": shared,
                    "status": status,
                    "cpu_percent": cpu_percent,
                    "mem_percent": mem_percent,
                    "time": time,
                    "command": command,
                }

                self.processes.append(proc_info)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        self.apply_filter(self.search.value)

    def on_input_changed(self, event: Input.Changed):
        self.apply_filter(event.value)


    def apply_filter(self, query=""):
        self.table.clear()
        query = query.strip().lower()
        for p in self.processes:
            if (
                query == ""
                or query in p["command"].lower()
                or query in str(p["pid"])
            ):
                self.table.add_row(
                    p['pid'], 
                    p['username'], 
                    p['nice'],
                    p['vms'],
                    p['rss'],
                    p['shared'],
                    p['status'],
                    p['cpu_percent'],
                    p['mem_percent'],
                    p['time'],
                    p['command']
                )