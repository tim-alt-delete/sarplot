"""End-to-end tests driving the Textual app."""

from __future__ import annotations

import asyncio

from textual.widgets import DataTable, Input, Select, SelectionList, Static

from sarplot.app import TAB_VIEWS, SarPlot
from sarplot.collectors import sar
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
