"""End-to-end tests driving the Textual app."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from textual.widgets import (
    Checkbox,
    DataTable,
    DirectoryTree,
    Input,
    RichLog,
    Select,
    SelectionList,
    Static,
)

from sarplot.app import TAB_VIEWS, SarPlot
from sarplot.collectors import logs, sar
from sarplot.views.process_view import COLUMNS
from sarplot.widgets.confirm import ConfirmScreen
from sarplot.widgets.prompt import IntPromptScreen

COLUMN_INDEX = {column.key: index for index, column in enumerate(COLUMNS)}
SIZE = (150, 45)


async def settle(pilot, seconds: float = 0.3) -> None:
    """Let timers fire and workers finish."""
    await pilot.pause()
    await asyncio.sleep(seconds)
    await pilot.pause()


def text_of(widget: Static) -> str:
    """The text a Static is currently displaying."""
    return str(widget.content)


class TestAppSmoke:
    async def test_every_tab_mounts_without_error(self):
        app = SarPlot()
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            for tab in TAB_VIEWS:
                app.query_one("#tabs").active = tab
                await settle(pilot)
            assert app.query_one("#tabs").active == "tab-system"

    async def test_starts_on_the_requested_tab(self):
        app = SarPlot(initial_tab="tab-system")
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            assert app.query_one("#tabs").active == "tab-system"

    async def test_theme_toggles_between_light_and_dark(self):
        app = SarPlot()
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            before = app.theme
            app.action_toggle_theme()
            await pilot.pause()
            assert app.theme != before
            app.action_toggle_theme()
            await pilot.pause()
            assert app.theme == before


class TestTimerPausing:
    async def test_only_the_active_tab_polls(self):
        """Hidden views must not keep waking the process every second."""
        app = SarPlot()
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)

            processes = app.query_one("#processes")
            system = app.query_one("#system")
            live = app.query_one("#live")

            # Processes is the active tab at startup; the others are hidden.
            assert processes._timer._active.is_set() is True
            assert system._timer._active.is_set() is False
            assert live._timer._active.is_set() is False

            app.query_one("#tabs").active = "tab-system"
            await settle(pilot)

            assert system._timer._active.is_set() is True
            assert processes._timer._active.is_set() is False
            assert live._timer._active.is_set() is False


class TestProcessView:
    async def test_table_is_populated(self):
        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            table = app.query_one("#proc-table", DataTable)
            assert table.row_count > 0
            assert len(table.columns) == len(COLUMNS)

    async def test_filter_narrows_the_table(self):
        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            table = app.query_one("#proc-table", DataTable)
            total = table.row_count

            app.query_one("#proc-search", Input).value = "definitely-no-such-process"
            await settle(pilot)
            assert table.row_count == 0

            app.query_one("#proc-search", Input).value = ""
            await settle(pilot)
            assert table.row_count == total

    async def test_filter_matches_pid(self):
        import os

        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#proc-search", Input).value = str(os.getpid())
            await settle(pilot)
            assert app.query_one("#proc-table", DataTable).row_count >= 1

    async def test_sorting_reorders_rows(self):
        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            view = app.query_one("#processes")
            table = app.query_one("#proc-table", DataTable)

            def column(key, count=8):
                return [
                    str(table.get_row_at(i)[COLUMN_INDEX[key]])
                    for i in range(min(count, table.row_count))
                ]

            view.action_sort("pid")
            await pilot.pause()
            descending = column("pid")
            assert descending == sorted(descending, key=int, reverse=True)

            # Sorting by the same column again flips the direction.
            view.action_sort("pid")
            await pilot.pause()
            ascending = column("pid")
            assert ascending == sorted(ascending, key=int)

    async def test_cursor_stays_on_the_same_process_across_a_refresh(self):
        """Regression: clearing and rebuilding the table reset the cursor
        every refresh, making a process impossible to keep track of."""
        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            view = app.query_one("#processes")
            table = app.query_one("#proc-table", DataTable)

            table.move_cursor(row=min(4, table.row_count - 1))
            await pilot.pause()
            before = view._selected_pid()
            assert before is not None

            view.refresh_processes()
            await pilot.pause()
            assert view._selected_pid() == before

    async def test_rows_are_reused_rather_than_recreated(self):
        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            view = app.query_one("#processes")
            keys_before = dict(view._rows)

            view.refresh_processes()
            await pilot.pause()

            survivors = set(keys_before) & set(view._rows)
            assert survivors, "expected most processes to persist across a refresh"
            for pid in survivors:
                assert view._rows[pid] is keys_before[pid]

    async def test_header_reports_real_host_facts(self):
        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            header = text_of(app.query_one("#proc-header", Static))
            assert "Uptime" in header
            assert "Load" in header
            assert "Tasks" in header


class TestProcessActions:
    async def test_terminate_opens_a_confirmation_first(self):
        """Destructive actions must never fire straight off a keypress."""
        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            table = app.query_one("#proc-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            app.query_one("#processes").action_terminate()
            await settle(pilot)
            assert isinstance(app.screen, ConfirmScreen)

            await pilot.press("escape")
            await settle(pilot)
            assert not isinstance(app.screen, ConfirmScreen)

    async def test_confirmation_names_the_target_process(self):
        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            view = app.query_one("#processes")
            app.query_one("#proc-table", DataTable).move_cursor(row=0)
            await pilot.pause()

            pid = view._selected_pid()
            view.action_terminate()
            await settle(pilot)

            detail = text_of(app.screen.query_one("#confirm-detail", Static))
            assert str(pid) in detail

    async def test_kill_warns_that_sigkill_cannot_be_caught(self):
        app = SarPlot(refresh=0.5)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#proc-table", DataTable).move_cursor(row=0)
            await pilot.pause()

            app.query_one("#processes").action_kill()
            await settle(pilot)
            detail = text_of(app.screen.query_one("#confirm-detail", Static))
            assert "SIGKILL" in detail

    async def test_terminating_a_real_child_process_works(self):
        """The full path: select, confirm, signal, and observe it exit."""
        import subprocess

        child = subprocess.Popen(["sleep", "300"])
        try:
            app = SarPlot(refresh=0.5)
            async with app.run_test(size=SIZE) as pilot:
                await settle(pilot, 0.8)
                view = app.query_one("#processes")

                assert child.pid in view._by_pid, "child should appear in the table"

                view._send_signal(view._by_pid[child.pid], force=False)
                await settle(pilot, 0.5)
                assert child.poll() is not None, "child should have exited"
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()


class TestRenice:
    @staticmethod
    async def _open_prompt(app, pilot, pid):
        view = app.query_one("#processes")
        view._filter = str(pid)
        view._sync_table()
        await pilot.pause()
        app.query_one("#proc-table", DataTable).move_cursor(row=0)
        await pilot.pause()
        view.action_renice()
        await settle(pilot)
        return view

    async def test_renices_a_real_child_process(self):
        import subprocess

        import psutil

        child = subprocess.Popen(["sleep", "300"])
        try:
            app = SarPlot(refresh=0.5)
            async with app.run_test(size=SIZE) as pilot:
                await settle(pilot, 0.8)
                await self._open_prompt(app, pilot, child.pid)
                assert isinstance(app.screen, IntPromptScreen)

                app.screen.query_one("#prompt-input", Input).value = "5"
                app.screen._on_submit()
                await settle(pilot, 0.4)

                assert not isinstance(app.screen, IntPromptScreen)
                assert psutil.Process(child.pid).nice() == 5
        finally:
            child.kill()
            child.wait()

    async def test_rejects_a_non_numeric_value_without_closing(self):
        import subprocess

        child = subprocess.Popen(["sleep", "300"])
        try:
            app = SarPlot(refresh=0.5)
            async with app.run_test(size=SIZE) as pilot:
                await settle(pilot, 0.8)
                await self._open_prompt(app, pilot, child.pid)

                app.screen.query_one("#prompt-input", Input).value = "abc"
                app.screen._on_submit()
                await pilot.pause()

                assert isinstance(app.screen, IntPromptScreen)
                error = text_of(app.screen.query_one("#prompt-error", Static))
                assert "whole number" in error
        finally:
            child.kill()
            child.wait()

    async def test_enforces_the_nice_range(self):
        import subprocess

        child = subprocess.Popen(["sleep", "300"])
        try:
            app = SarPlot(refresh=0.5)
            async with app.run_test(size=SIZE) as pilot:
                await settle(pilot, 0.8)
                await self._open_prompt(app, pilot, child.pid)

                app.screen.query_one("#prompt-input", Input).value = "99"
                app.screen._on_submit()
                await pilot.pause()

                assert isinstance(app.screen, IntPromptScreen)
                assert "19" in text_of(app.screen.query_one("#prompt-error", Static))
        finally:
            child.kill()
            child.wait()

    async def test_escape_cancels_without_changing_anything(self):
        import subprocess

        import psutil

        child = subprocess.Popen(["sleep", "300"])
        try:
            before = psutil.Process(child.pid).nice()
            app = SarPlot(refresh=0.5)
            async with app.run_test(size=SIZE) as pilot:
                await settle(pilot, 0.8)
                await self._open_prompt(app, pilot, child.pid)

                await pilot.press("escape")
                await settle(pilot)

                assert not isinstance(app.screen, IntPromptScreen)
                assert psutil.Process(child.pid).nice() == before
        finally:
            child.kill()
            child.wait()


class TestHistoryView:
    async def test_reads_a_real_archive(self, sar_archive):
        """Drives the real sadf binary against a freshly collected archive."""
        app = SarPlot(sa_file=str(sar_archive), initial_tab="tab-history")
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 1.5)

            status = text_of(app.query_one("#history-status", Static))
            assert "samples" in status

            selection = app.query_one("#series-select", SelectionList)
            assert len(selection._options) > 0
            assert selection.selected, "expected default series to be preselected"

    async def test_changing_metric_reloads_series(self, sar_archive):
        app = SarPlot(sa_file=str(sar_archive), initial_tab="tab-history")
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 1.5)
            selection = app.query_one("#series-select", SelectionList)
            cpu_series = {option.value for option in selection._options}

            app.query_one("#metric-select", Select).value = "memory"
            await settle(pilot, 1.5)

            memory_series = {option.value for option in selection._options}
            assert memory_series != cpu_series
            assert "memused" in memory_series

    async def test_invalid_time_is_reported_not_raised(self, sar_archive):
        app = SarPlot(sa_file=str(sar_archive), initial_tab="tab-history")
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 1.2)
            app.query_one("#start-input", Input).value = "banana"
            app.query_one("#history").reload()
            await settle(pilot)

            status = app.query_one("#history-status", Static)
            assert "Invalid start time" in text_of(status)
            assert status.has_class("-error")

    async def test_degrades_gracefully_without_sysstat(self, monkeypatch):
        """The old code raised an uncaught CalledProcessError here and took
        the whole app down."""
        monkeypatch.setattr(sar, "LOG_DIRECTORIES", ("/nonexistent",))

        app = SarPlot(initial_tab="tab-history")
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            panel = app.query_one("#history-unavailable", Static)
            text = text_of(panel)
            assert "unavailable" in text.lower()
            assert "sysstat" in text
            # The rest of the app keeps working.
            app.query_one("#tabs").active = "tab-processes"
            await settle(pilot)
            assert app.query_one("#proc-table", DataTable).row_count > 0


class TestSystemView:
    async def test_panels_are_populated(self):
        app = SarPlot(initial_tab="tab-system")
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.5)

            host = text_of(app.query_one("#host-info", Static))
            assert "Hostname" in host
            assert "Kernel" in host

            resources = text_of(app.query_one("#resource-info", Static))
            assert "Memory" in resources
            assert "Cores" in resources

            assert app.query_one("#disk-table", DataTable).row_count > 0
            assert app.query_one("#net-table", DataTable).row_count > 0

    async def test_panels_have_titles(self):
        app = SarPlot(initial_tab="tab-system")
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.5)
            assert app.query_one("#host-panel").border_title == "Host"
            assert app.query_one("#disk-panel").border_title == "Filesystems"


class TestLiveView:
    async def test_samples_accumulate_over_time(self):
        app = SarPlot(initial_tab="tab-live")
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 2.5)
            view = app.query_one("#live")
            assert len(view._history) > 0
            assert "total" in view._history.names

    async def test_switching_metric_resets_history(self):
        app = SarPlot(initial_tab="tab-live")
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 2.0)
            view = app.query_one("#live")

            app.query_one("#live-metric-select", Select).value = "memory"
            await settle(pilot, 1.5)

            assert "memory" in view._history.names
            assert "total" not in view._history.names


def make_log(directory: Path, name: str = "app.log", count: int = 30) -> Path:
    """Write a log with a predictable mix of severities."""
    path = directory / name
    path.write_text(
        "".join(
            f"2026-08-30 10:{i:02d}:00 host app[42]: "
            + (
                "ERROR database timeout"
                if i % 7 == 0
                else "WARNING slow query"
                if i % 5 == 0
                else "request handled ok"
            )
            + "\n"
            for i in range(count)
        )
    )
    return path


class TestLogView:
    async def test_opens_the_requested_file(self, tmp_path):
        path = make_log(tmp_path)
        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            assert app.query_one("#log-main").border_title == str(path)
            assert app.query_one("#log-output", RichLog).lines
            assert "30 lines" in text_of(app.query_one("#log-status", Static))

    async def test_bracketed_text_survives_rendering(self, tmp_path):
        """RichLog(markup=True) would eat program[pid], which is the syslog
        format, so lines must be written as Text objects."""
        path = tmp_path / "b.log"
        path.write_text("Aug 30 10:49:01 host sshd[1234]: Accepted for [alice]\n")

        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            rendered = app.query_one("#log-output", RichLog).lines[0].text
            assert "sshd[1234]" in rendered
            assert "[alice]" in rendered

    async def test_tree_is_rooted_at_the_log_directory(self, tmp_path):
        make_log(tmp_path)
        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            assert app.query_one("#log-tree", DirectoryTree).path == tmp_path

    async def test_tree_hides_binaries_and_unreadable_files(self, tmp_path):
        make_log(tmp_path, "good.log")
        (tmp_path / "wtmp").write_bytes(b"")
        (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02\x03")
        (tmp_path / ".hidden").write_text("secret\n")

        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            tree = app.query_one("#log-tree", DirectoryTree)
            kept = {p.name for p in tree.filter_paths(sorted(tmp_path.iterdir()))}
            assert kept == {"good.log"}

    async def test_selecting_a_file_loads_it(self, tmp_path):
        make_log(tmp_path, "first.log")
        second = make_log(tmp_path, "second.log", count=5)

        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#logs").open_path(second)
            await settle(pilot)

            assert app.query_one("#log-main").border_title == str(second)
            assert "5 lines" in text_of(app.query_one("#log-status", Static))

    async def test_unreadable_file_reports_instead_of_crashing(self, tmp_path):
        blob = tmp_path / "blob.bin"
        blob.write_bytes(b"\x00\x01\x02binary\x00")

        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#logs").open_path(blob)
            await settle(pilot)

            assert "binary" in text_of(app.query_one("#log-status", Static))
            assert app._exception is None

    async def test_empty_directory_explains_itself(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "SYSTEM_LOG_CANDIDATES", ())
        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            status = text_of(app.query_one("#log-status", Static))
            assert "No" in status
            assert app._exception is None


class TestLogSearch:
    @staticmethod
    async def _open(tmp_path, pilot_size=SIZE):
        path = make_log(tmp_path)
        return SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))

    async def test_filter_hides_non_matching_lines(self, tmp_path):
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            output = app.query_one("#log-output", RichLog)
            assert len(output.lines) == 30

            app.query_one("#log-search", Input).value = "ERROR"
            await settle(pilot)

            assert len(output.lines) == 5
            assert all("ERROR" in strip.text for strip in output.lines)

    async def test_clearing_the_filter_restores_every_line(self, tmp_path):
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            output = app.query_one("#log-output", RichLog)

            app.query_one("#log-search", Input).value = "ERROR"
            await settle(pilot)
            app.query_one("#log-search", Input).value = ""
            await settle(pilot)

            assert len(output.lines) == 30

    async def test_search_is_case_insensitive_by_default(self, tmp_path):
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#log-search", Input).value = "error"
            await settle(pilot)
            assert len(app.query_one("#log-output", RichLog).lines) == 5

    async def test_case_toggle_makes_the_search_exact(self, tmp_path):
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#log-case", Checkbox).value = True
            app.query_one("#log-search", Input).value = "error"
            await settle(pilot)
            assert len(app.query_one("#log-output", RichLog).lines) == 0

    async def test_literal_search_does_not_treat_input_as_regex(self, tmp_path):
        """'app[42]' must match literally when the regex toggle is off."""
        path = tmp_path / "b.log"
        path.write_text("host app[42]: hello\nhost appX: world\n")
        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#log-search", Input).value = "app[42]"
            await settle(pilot)

            lines = app.query_one("#log-output", RichLog).lines
            assert len(lines) == 1
            assert "app[42]" in lines[0].text

    async def test_regex_toggle_enables_patterns(self, tmp_path):
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#log-regex", Checkbox).value = True
            app.query_one("#log-search", Input).value = "ERROR|WARNING"
            await settle(pilot)

            output = app.query_one("#log-output", RichLog)
            assert len(output.lines) > 5
            assert all("ERROR" in strip.text or "WARNING" in strip.text for strip in output.lines)

    async def test_invalid_regex_is_reported_not_raised(self, tmp_path):
        """A half-typed pattern is a normal intermediate state."""
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#log-regex", Checkbox).value = True
            app.query_one("#log-search", Input).value = "unclosed["
            await settle(pilot)

            status = app.query_one("#log-status", Static)
            assert "Invalid regular expression" in text_of(status)
            assert status.has_class("-error")
            assert app._exception is None

    async def test_invalid_regex_keeps_the_previous_results(self, tmp_path):
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            output = app.query_one("#log-output", RichLog)

            app.query_one("#log-regex", Checkbox).value = True
            app.query_one("#log-search", Input).value = "ERROR"
            await settle(pilot)
            good = len(output.lines)

            app.query_one("#log-search", Input).value = "ERROR("
            await settle(pilot)
            assert len(output.lines) == good

    async def test_highlight_mode_keeps_every_line(self, tmp_path):
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            app.query_one("#log-filter-mode", Checkbox).value = False
            app.query_one("#log-search", Input).value = "ERROR"
            await settle(pilot)

            assert len(app.query_one("#log-output", RichLog).lines) == 30
            assert "highlighted" in text_of(app.query_one("#log-status", Static))

    async def test_next_match_scrolls_between_matches(self, tmp_path):
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            view = app.query_one("#logs")
            app.query_one("#log-filter-mode", Checkbox).value = False
            app.query_one("#log-search", Input).value = "ERROR"
            await settle(pilot)

            assert len(view._match_offsets) == 5
            view.action_next_match()
            await pilot.pause()
            first = view._match_index
            view.action_next_match()
            await pilot.pause()
            assert view._match_index == first + 1

    async def test_match_jumping_wraps_around(self, tmp_path):
        app = await self._open(tmp_path)
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            view = app.query_one("#logs")
            app.query_one("#log-filter-mode", Checkbox).value = False
            app.query_one("#log-search", Input).value = "ERROR"
            await settle(pilot)

            view.action_previous_match()
            await pilot.pause()
            assert view._match_index == len(view._match_offsets) - 1


class TestLogFollow:
    async def test_appended_lines_appear(self, tmp_path):
        path = make_log(tmp_path, count=5)
        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            output = app.query_one("#log-output", RichLog)
            assert len(output.lines) == 5

            with path.open("a") as handle:
                handle.write("brand new line\n")
            await settle(pilot, 1.2)

            assert len(output.lines) == 6
            assert "brand new line" in output.lines[-1].text

    async def test_rotation_reloads_the_pane(self, tmp_path):
        path = make_log(tmp_path, count=5)
        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            output = app.query_one("#log-output", RichLog)

            os.rename(path, tmp_path / "app.log.1")
            path.write_text("after rotation\n")
            await settle(pilot, 1.2)

            assert len(output.lines) == 1
            assert "after rotation" in output.lines[0].text

    async def test_unfollowed_pane_ignores_appends(self, tmp_path):
        path = make_log(tmp_path, count=5)
        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            output = app.query_one("#log-output", RichLog)

            app.query_one("#log-follow", Checkbox).value = False
            await settle(pilot)

            with path.open("a") as handle:
                handle.write("ignored\n")
            await settle(pilot, 1.2)

            assert len(output.lines) == 5
            assert "paused" in text_of(app.query_one("#log-status", Static))

    async def test_polling_pauses_when_the_tab_is_hidden(self):
        app = SarPlot()
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            view = app.query_one("#logs")
            assert view._timer._active.is_set() is False

            app.query_one("#tabs").active = "tab-logs"
            await settle(pilot)
            assert view._timer._active.is_set() is True

    async def test_compressed_archive_is_read_but_not_followed(self, tmp_path):
        import gzip

        path = tmp_path / "old.log.gz"
        with gzip.open(path, "wb") as handle:
            handle.write(b"".join(f"archived {i}\n".encode() for i in range(4)))

        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            assert len(app.query_one("#log-output", RichLog).lines) == 4
            assert "not followable" in text_of(app.query_one("#log-status", Static))

    async def test_tree_hides_unreadable_directories(self, tmp_path):
        """An unreadable directory expands to nothing with no explanation."""
        if os.geteuid() == 0:
            pytest.skip("root bypasses directory permissions")

        make_log(tmp_path, "good.log")
        (tmp_path / "visible").mkdir()
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        blocked.chmod(0o000)

        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path))
        try:
            async with app.run_test(size=SIZE) as pilot:
                await settle(pilot, 0.6)
                tree = app.query_one("#log-tree", DirectoryTree)
                kept = {p.name for p in tree.filter_paths(sorted(tmp_path.iterdir()))}
                assert kept == {"good.log", "visible"}
        finally:
            blocked.chmod(0o755)


class TestLogSeverityStyling:
    async def test_severity_lines_are_actually_styled(self, tmp_path):
        """Regression: styles were written as '$text-error', which Rich does
        not understand, so every line rendered unstyled."""
        path = tmp_path / "s.log"
        path.write_text("plain line\nERROR bad thing\nWARNING careful\n")

        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)
            lines = app.query_one("#log-output", RichLog).lines

            def first_style(strip):
                for segment in strip._segments:
                    if segment.text.strip():
                        return str(segment.style)
                return ""

            assert first_style(lines[0]) in ("None", "none", "")
            assert first_style(lines[1]) not in ("None", "none", "")
            assert first_style(lines[2]) not in ("None", "none", "")

    async def test_styles_follow_the_app_theme(self, tmp_path):
        path = tmp_path / "s.log"
        path.write_text("ERROR bad thing\n")

        app = SarPlot(initial_tab="tab-logs", log_dir=str(tmp_path), log_file=str(path))
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, 0.6)

            def error_style():
                strip = app.query_one("#log-output", RichLog).lines[0]
                return str(next(s.style for s in strip._segments if s.text.strip()))

            before = error_style()
            app.action_toggle_theme()
            await settle(pilot, 0.4)
            assert error_style() != before
