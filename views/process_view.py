from textual.containers import Container, Grid, Vertical
from textual.widgets import DataTable, Input
import psutil

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