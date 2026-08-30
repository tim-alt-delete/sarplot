from textual.containers import Vertical
from textual.widgets import DataTable, Input, Static
from utils.system import get_uptime, get_load_avg
from utils.process import get_processes, PROC_STATES
from utils.helpers import format_bytes
import platform
import psutil

class ProcessView(Vertical):
    def compose(self):
        yield Static(id="header")
        yield Input(placeholder="Search process...", id="search")
        yield DataTable(id="proc_table")

    def on_mount(self):
        self.set_interval(2.0, self.refresh_processes) # every 2 seconds
        self.set_interval(15.0, self.update_header) # every 15 seconds

        self.table = self.query_one("#proc_table", DataTable)
        self.table.add_columns("PID", "USER", "NI", "VIRT", "RES", "SHR", "S", "CPU%", "MEM%", "TIME+", "Command")
        self.table.zebra_stripes = True
        self.table.cursor_type = "row"

        self.search = self.query_one("#search", Input)

        self.header = self.query_one("#header", Static)

        self.processes = []  # Store all processes for filtering
        self.refresh_processes()
        self.update_header()

    def update_header(self):
        uptime = get_uptime()        # e.g. "1 day, 02:34"
        load_avg = get_load_avg()    # e.g. "0.12 0.10 0.08"
        cpu = f"{platform.processor() or 'CPU'}"
        text = f"Uptime: {uptime}\nLoad: {round(load_avg[0], 2)} {round(load_avg[1], 2)} {round(load_avg[2], 2)}\n{cpu}\nTasks: {len(self.processes)}"
        self.header.update(text)

    def refresh_processes(self):
        self.processes = get_processes()
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