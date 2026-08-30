"""An interactive, sortable process table."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

import psutil
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Input, Static

from sarplot.collectors import processes as proc
from sarplot.collectors import system
from sarplot.formatting import format_bytes, format_cpu_time, format_percent
from sarplot.widgets.confirm import ConfirmScreen
from sarplot.widgets.prompt import IntPromptScreen


@dataclass(frozen=True)
class Column:
    """A table column and the ProcessInfo field it sorts on."""

    key: str
    label: str
    field: str
    numeric: bool = True
    #: Most numeric columns are most useful largest-first.
    descending: bool = True


COLUMNS: tuple[Column, ...] = (
    Column("pid", "PID", "pid"),
    Column("user", "USER", "username", numeric=False, descending=False),
    Column("nice", "NI", "nice"),
    Column("virt", "VIRT", "vms"),
    Column("res", "RES", "rss"),
    Column("shr", "SHR", "shared"),
    Column("state", "S", "status", numeric=False, descending=False),
    Column("cpu", "CPU%", "cpu_percent"),
    Column("mem", "MEM%", "mem_percent"),
    Column("time", "TIME+", "cpu_time"),
    Column("command", "Command", "command", numeric=False, descending=False),
)

COLUMNS_BY_KEY = {c.key: c for c in COLUMNS}


class ProcessView(Vertical):
    """Live process list.

    Rows are updated in place and keyed by PID so the cursor stays on the
    process the user selected, even as it moves in the sort order.
    """

    BINDINGS = [
        Binding("slash", "focus_search", "Search"),
        Binding("c", "sort('cpu')", "Sort CPU"),
        Binding("m", "sort('mem')", "Sort MEM"),
        Binding("p", "sort('pid')", "Sort PID"),
        Binding("t", "sort('time')", "Sort TIME"),
        Binding("i", "invert_sort", "Reverse"),
        Binding("k", "terminate", "Terminate"),
        Binding("K", "kill", "Kill"),
        Binding("n", "renice", "Renice"),
        Binding("escape", "clear_search", "Clear search", show=False),
    ]

    def __init__(self, *, interval: float = 2.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._interval = interval
        self._processes: list[proc.ProcessInfo] = []
        self._by_pid: dict[int, proc.ProcessInfo] = {}
        self._rows: dict[int, str] = {}
        self._rendered: dict[int, tuple] = {}
        self._sort_key = "cpu"
        self._sort_reverse = True
        self._filter = ""
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Static(id="proc-header")
        yield Input(placeholder="Filter by pid, user or command...", id="proc-search")
        yield DataTable(id="proc-table")
        yield Static(id="proc-status")

    def on_mount(self) -> None:
        table = self.query_one("#proc-table", DataTable)
        for column in COLUMNS:
            table.add_column(column.label, key=column.key)
        table.zebra_stripes = True
        table.cursor_type = "row"

        self._timer = self.set_interval(self._interval, self.refresh_processes)
        self.refresh_processes()

    def pause(self) -> None:
        """Stop polling while the tab is hidden."""
        if self._timer is not None:
            self._timer.pause()

    def resume(self) -> None:
        if self._timer is not None:
            self._timer.resume()
            self.refresh_processes()

    # ------------------------------------------------------------------ data

    def refresh_processes(self) -> None:
        self._processes = proc.get_processes()
        self._by_pid = {p.pid: p for p in self._processes}
        self._sync_table()
        self._update_header()

    def _visible(self) -> list[proc.ProcessInfo]:
        """Apply the current filter."""
        if not self._filter:
            return self._processes
        needle = self._filter
        return [
            p
            for p in self._processes
            if needle in p.command.lower()
            or needle in p.username.lower()
            or needle in str(p.pid)
        ]

    @staticmethod
    def _cells(p: proc.ProcessInfo) -> tuple:
        """Render one process into display cells.

        Numeric columns are right-justified so magnitudes line up.
        """
        right = lambda text: Text(text, justify="right")  # noqa: E731
        return (
            right(str(p.pid)),
            p.username,
            right(str(p.nice)),
            right(format_bytes(p.vms)),
            right(format_bytes(p.rss)),
            right(format_bytes(p.shared)),
            p.status,
            right(format_percent(p.cpu_percent)),
            right(format_percent(p.mem_percent)),
            right(format_cpu_time(p.cpu_time)),
            p.command,
        )

    def _sync_table(self) -> None:
        """Reconcile the table with the current snapshot.

        Rows are added, updated and removed individually instead of clearing
        and rebuilding, which would reset the cursor and scroll offset on
        every refresh.
        """
        table = self.query_one("#proc-table", DataTable)
        visible = self._visible()
        wanted = {p.pid for p in visible}

        selected_pid = self._selected_pid()

        for pid in list(self._rows):
            if pid not in wanted:
                with contextlib.suppress(KeyError):
                    table.remove_row(self._rows[pid])
                del self._rows[pid]
                self._rendered.pop(pid, None)

        for p in visible:
            cells = self._cells(p)
            if p.pid in self._rows:
                previous = self._rendered.get(p.pid)
                if previous == cells:
                    continue
                row_key = self._rows[p.pid]
                for index, (column, value) in enumerate(zip(COLUMNS, cells, strict=True)):
                    # Only touch cells that actually changed; each update
                    # invalidates and redraws a region.
                    if previous is None or previous[index] != value:
                        table.update_cell(row_key, column.key, value)
            else:
                self._rows[p.pid] = table.add_row(*cells, key=str(p.pid))
            self._rendered[p.pid] = cells

        self._apply_sort(table)

        if selected_pid is not None:
            self._restore_cursor(table, selected_pid)

    def _apply_sort(self, table: DataTable) -> None:
        column = COLUMNS_BY_KEY[self._sort_key]

        def sort_value(cell):
            # The PID column carries the identity we look the process up by.
            raw = cell.plain if isinstance(cell, Text) else cell
            try:
                info = self._by_pid[int(raw)]
            except (KeyError, TypeError, ValueError):
                return 0 if column.numeric else ""
            value = getattr(info, column.field)
            return value.lower() if isinstance(value, str) else value

        table.sort("pid", key=sort_value, reverse=self._sort_reverse)

    def _selected_pid(self) -> int | None:
        table = self.query_one("#proc-table", DataTable)
        if not table.is_mounted or table.row_count == 0:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return None
        try:
            return int(str(row_key.value))
        except (TypeError, ValueError):
            return None

    def _restore_cursor(self, table: DataTable, pid: int) -> None:
        """Return the cursor to a process after rows were reordered."""
        row_key = self._rows.get(pid)
        if row_key is None:
            return
        try:
            index = table.get_row_index(row_key)
        except KeyError:
            return
        table.move_cursor(row=index, scroll=False)

    # ---------------------------------------------------------------- header

    def _update_header(self) -> None:
        one, five, fifteen = system.get_load_avg()
        physical, logical = system.get_cpu_counts()
        memory = psutil.virtual_memory()

        running = sum(1 for p in self._processes if p.status == "R")
        threads = sum(1 for p in self._processes if p.is_zombie)

        lines = [
            f"[b]{system.get_cpu_model()}[/b]  ({physical}C / {logical}T)",
            f"Uptime {system.get_uptime()}    "
            f"Load {one:.2f} {five:.2f} {fifteen:.2f}",
            f"Tasks {len(self._processes)} ({running} running"
            + (f", {threads} zombie" if threads else "")
            + ")    "
            f"Mem {format_bytes(memory.used)} / {format_bytes(memory.total)} "
            f"({memory.percent:.1f}%)",
        ]
        self.query_one("#proc-header", Static).update("\n".join(lines))

        column = COLUMNS_BY_KEY[self._sort_key]
        order = "desc" if self._sort_reverse else "asc"
        shown = len(self._visible())
        status = f"Sorted by {column.label} ({order})"
        if self._filter:
            status += f"    Filter '{self._filter}' - {shown} of {len(self._processes)}"
        if not system.is_root():
            status += "    Running unprivileged: some processes are hidden"
        self.query_one("#proc-status", Static).update(status)

    # ---------------------------------------------------------------- events

    @on(Input.Changed, "#proc-search")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        self._filter = event.value.strip().lower()
        self._sync_table()
        self._update_header()

    @on(DataTable.HeaderSelected, "#proc-table")
    def _on_header_selected(self, event: DataTable.HeaderSelected) -> None:
        self.action_sort(str(event.column_key.value))

    # --------------------------------------------------------------- actions

    def action_focus_search(self) -> None:
        self.query_one("#proc-search", Input).focus()

    def action_clear_search(self) -> None:
        search = self.query_one("#proc-search", Input)
        search.value = ""
        self.query_one("#proc-table", DataTable).focus()

    def action_sort(self, key: str) -> None:
        column = COLUMNS_BY_KEY.get(key)
        if column is None:
            return
        if self._sort_key == key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = key
            self._sort_reverse = column.descending
        self._sync_table()
        self._update_header()

    def action_invert_sort(self) -> None:
        self._sort_reverse = not self._sort_reverse
        self._sync_table()
        self._update_header()

    def _target(self) -> proc.ProcessInfo | None:
        """The process under the cursor, if any."""
        pid = self._selected_pid()
        if pid is None:
            self.notify("Select a process first.", severity="warning")
            return None
        info = self._by_pid.get(pid)
        if info is None:
            self.notify("That process is no longer running.", severity="warning")
            return None
        return info

    def action_terminate(self) -> None:
        self._confirm_signal(force=False)

    def action_kill(self) -> None:
        self._confirm_signal(force=True)

    def _confirm_signal(self, *, force: bool) -> None:
        info = self._target()
        if info is None:
            return

        signal_name = "SIGKILL" if force else "SIGTERM"
        warning = ""
        if not proc.can_signal(info.pid):
            warning = "\n\nThis process belongs to another user; this will likely fail."
        if force:
            warning += "\n\nSIGKILL cannot be caught: the process will not clean up."

        detail = (
            f"PID:     {info.pid}\n"
            f"User:    {info.username}\n"
            f"Command: {info.command[:100]}"
            f"{warning}"
        )

        def respond(confirmed: bool | None) -> None:
            if confirmed:
                self._send_signal(info, force=force)

        self.app.push_screen(
            ConfirmScreen(
                f"Send {signal_name} to process {info.pid}?",
                detail,
                confirm_label=signal_name,
            ),
            respond,
        )

    def _send_signal(self, info: proc.ProcessInfo, *, force: bool) -> None:
        signal_name = "SIGKILL" if force else "SIGTERM"
        try:
            proc.terminate(info.pid, force=force)
        except psutil.NoSuchProcess:
            self.notify(f"Process {info.pid} already exited.", severity="warning")
        except psutil.AccessDenied:
            self.notify(
                f"Permission denied sending {signal_name} to {info.pid}.",
                severity="error",
            )
        except psutil.Error as exc:
            self.notify(f"Failed to signal {info.pid}: {exc}", severity="error")
        else:
            self.notify(f"Sent {signal_name} to {info.pid} ({info.name}).")
            self.refresh_processes()

    def action_renice(self) -> None:
        info = self._target()
        if info is None:
            return

        note = ""
        if not system.is_root():
            note = "\n\nWithout root you can only raise the nice value (lower priority)."

        def respond(value: int | None) -> None:
            if value is not None:
                self._apply_nice(info, value)

        self.app.push_screen(
            IntPromptScreen(
                f"Renice process {info.pid}",
                f"Command: {info.command[:100]}\nCurrent nice: {info.nice}{note}",
                initial=info.nice,
                minimum=-20,
                maximum=19,
            ),
            respond,
        )

    def _apply_nice(self, info: proc.ProcessInfo, value: int) -> None:
        try:
            applied = proc.set_nice(info.pid, value)
        except psutil.NoSuchProcess:
            self.notify(f"Process {info.pid} already exited.", severity="warning")
        except psutil.AccessDenied:
            self.notify(
                f"Permission denied renicing {info.pid}. Lowering the nice value "
                "requires root.",
                severity="error",
            )
        except psutil.Error as exc:
            self.notify(f"Failed to renice {info.pid}: {exc}", severity="error")
        else:
            self.notify(f"Set nice of {info.pid} to {applied}.")
            self.refresh_processes()
