"""Tests for process collection."""

from __future__ import annotations

import psutil
import pytest

from sarplot.collectors import processes


class FakeMemoryInfo:
    def __init__(self, rss=1024, vms=4096, shared=512):
        self.rss = rss
        self.vms = vms
        self.shared = shared


class FakeMemoryInfoNoShared:
    """macOS and some BSDs omit `shared`."""

    def __init__(self, rss=1024, vms=4096):
        self.rss = rss
        self.vms = vms


class FakeCpuTimes:
    def __init__(self, user=1.5, system=0.5):
        self.user = user
        self.system = system


class FakeUids:
    def __init__(self, real=1000):
        self.real = real


class FakeProcess:
    """A psutil.Process stand-in with configurable failure modes."""

    def __init__(
        self,
        pid=1234,
        *,
        status="sleeping",
        cmdline=("/usr/bin/python3", "app.py"),
        name="python3",
        username="alice",
        memory=None,
        raises=None,
        cmdline_raises=None,
        username_raises=None,
        uid=1000,
    ):
        self.pid = pid
        self._status = status
        self._cmdline = list(cmdline)
        self._name = name
        self._username = username
        self._memory = memory or FakeMemoryInfo()
        self._raises = raises
        self._cmdline_raises = cmdline_raises
        self._username_raises = username_raises
        self._uid = uid

    def oneshot(self):
        class Ctx:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *args):
                return False

        return Ctx()

    def _check(self):
        if self._raises is not None:
            raise self._raises

    def memory_info(self):
        self._check()
        return self._memory

    def cpu_times(self):
        self._check()
        return FakeCpuTimes()

    def cmdline(self):
        if self._cmdline_raises is not None:
            raise self._cmdline_raises
        return self._cmdline

    def name(self):
        return self._name

    def username(self):
        if self._username_raises is not None:
            raise self._username_raises
        return self._username

    def uids(self):
        return FakeUids(self._uid)

    def nice(self):
        return 0

    def status(self):
        return self._status

    def cpu_percent(self):
        return 12.5

    def memory_percent(self):
        return 3.25


class TestReadProcess:
    def test_builds_a_populated_snapshot(self):
        info = processes._read_process(FakeProcess())
        assert info is not None
        assert info.pid == 1234
        assert info.username == "alice"
        assert info.command == "/usr/bin/python3 app.py"
        assert info.status == "S"
        assert info.cpu_percent == 12.5
        assert info.cpu_time == 2.0

    @pytest.mark.parametrize(
        ("status", "code"),
        [
            ("running", "R"),
            ("sleeping", "S"),
            ("disk-sleep", "D"),
            ("zombie", "Z"),
            ("stopped", "T"),
            ("idle", "I"),
        ],
    )
    def test_maps_status_to_a_single_letter(self, status, code):
        info = processes._read_process(FakeProcess(status=status))
        assert info.status == code

    def test_unknown_status_is_marked_rather_than_blank(self):
        """The original mapped unknown states to '', leaving an empty column."""
        info = processes._read_process(FakeProcess(status="brand-new-state"))
        assert info.status == "?"

    def test_zombies_are_flagged(self):
        assert processes._read_process(FakeProcess(status="zombie")).is_zombie

    @pytest.mark.parametrize(
        "error",
        [psutil.NoSuchProcess(1), psutil.AccessDenied(1), psutil.ZombieProcess(1), OSError()],
    )
    def test_inaccessible_processes_are_skipped(self, error):
        assert processes._read_process(FakeProcess(raises=error)) is None

    def test_falls_back_to_name_when_cmdline_is_hidden(self):
        """Kernel threads and protected processes deny access to argv."""
        info = processes._read_process(
            FakeProcess(cmdline_raises=psutil.AccessDenied(1), name="kthreadd")
        )
        assert info.command == "kthreadd"

    def test_falls_back_to_name_for_an_empty_cmdline(self):
        info = processes._read_process(FakeProcess(cmdline=(), name="kworker"))
        assert info.command == "kworker"

    def test_long_command_lines_are_truncated(self):
        info = processes._read_process(FakeProcess(cmdline=("x" * 5000,)))
        assert len(info.command) == processes.COMMAND_LIMIT

    def test_username_falls_back_to_uid(self):
        """A uid with no passwd entry, common in containers."""
        info = processes._read_process(
            FakeProcess(username_raises=KeyError("no passwd entry"), uid=1000)
        )
        assert info.username == "1000"

    def test_missing_shared_field_defaults_to_zero(self):
        """`shared` is Linux-only; absent on macOS and some BSDs."""
        info = processes._read_process(FakeProcess(memory=FakeMemoryInfoNoShared()))
        assert info.shared == 0

    def test_shared_is_numeric_so_it_can_be_formatted_and_sorted(self):
        """Regression: `shared` was passed through raw while vms/rss were
        formatted, producing a mixed-type column."""
        info = processes._read_process(FakeProcess())
        assert isinstance(info.shared, int)
        assert isinstance(info.vms, int)
        assert isinstance(info.rss, int)


class TestGetProcesses:
    def test_skips_processes_that_vanish_mid_iteration(self, monkeypatch):
        good = FakeProcess(pid=1)
        gone = FakeProcess(pid=2, raises=psutil.NoSuchProcess(2))
        denied = FakeProcess(pid=3, raises=psutil.AccessDenied(3))

        monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: [good, gone, denied])
        result = processes.get_processes()
        assert [p.pid for p in result] == [1]

    def test_returns_process_info_instances(self, monkeypatch):
        monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: [FakeProcess()])
        assert all(isinstance(p, processes.ProcessInfo) for p in processes.get_processes())

    def test_reads_the_real_process_table(self):
        """Sanity check against the live system: we must at least see ourselves."""
        import os

        pids = {p.pid for p in processes.get_processes()}
        assert os.getpid() in pids


class TestSetNice:
    def test_clamps_to_the_valid_range(self, monkeypatch):
        applied = {}

        class Proc:
            def __init__(self, pid):
                pass

            def nice(self, value):
                applied["value"] = value

        monkeypatch.setattr(psutil, "Process", Proc)

        assert processes.set_nice(1, 100) == 19
        assert applied["value"] == 19
        assert processes.set_nice(1, -100) == -20
        assert applied["value"] == -20
        assert processes.set_nice(1, 5) == 5


class TestTerminate:
    def test_sends_sigterm_by_default(self, monkeypatch):
        calls = []

        class Proc:
            def __init__(self, pid):
                pass

            def terminate(self):
                calls.append("terminate")

            def kill(self):
                calls.append("kill")

        monkeypatch.setattr(psutil, "Process", Proc)
        processes.terminate(1)
        assert calls == ["terminate"]

    def test_force_sends_sigkill(self, monkeypatch):
        calls = []

        class Proc:
            def __init__(self, pid):
                pass

            def terminate(self):
                calls.append("terminate")

            def kill(self):
                calls.append("kill")

        monkeypatch.setattr(psutil, "Process", Proc)
        processes.terminate(1, force=True)
        assert calls == ["kill"]


class TestCanSignal:
    def test_root_can_signal_anything(self, monkeypatch):
        monkeypatch.setattr(processes.os, "geteuid", lambda: 0)
        assert processes.can_signal(1) is True

    def test_matching_uid_can_signal(self, monkeypatch):
        monkeypatch.setattr(processes.os, "geteuid", lambda: 1000)
        monkeypatch.setattr(processes.os, "getuid", lambda: 1000)
        monkeypatch.setattr(psutil, "Process", lambda pid: FakeProcess(uid=1000))
        assert processes.can_signal(1) is True

    def test_other_users_process_cannot_be_signalled(self, monkeypatch):
        monkeypatch.setattr(processes.os, "geteuid", lambda: 1000)
        monkeypatch.setattr(processes.os, "getuid", lambda: 1000)
        monkeypatch.setattr(psutil, "Process", lambda pid: FakeProcess(uid=0))
        assert processes.can_signal(1) is False

    def test_vanished_process_is_not_signallable(self, monkeypatch):
        monkeypatch.setattr(processes.os, "geteuid", lambda: 1000)

        def boom(pid):
            raise psutil.NoSuchProcess(pid)

        monkeypatch.setattr(psutil, "Process", boom)
        assert processes.can_signal(1) is False
