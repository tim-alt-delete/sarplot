"""Tests for the systemd journal scaffold.

Only the implemented parts are covered. The streaming functions are asserted
to raise NotImplementedError so the deferred work cannot rot silently into
something that looks finished.

The fixtures these read are synthetic - see the warning in
sarplot/collectors/journal.py.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from sarplot.collectors import journal
from sarplot.collectors.logs import Level, LogLine

FIXTURES = Path(__file__).parent / "fixtures" / "journal"


def load(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text()


class TestAvailability:
    def test_requires_both_the_binary_and_a_journal(self, monkeypatch):
        """journalctl exits 0 with an empty journal, printing '-- No entries --'
        to stdout and 'No journal files were found.' to stderr, so neither the
        binary's presence nor the exit status is sufficient on its own."""
        monkeypatch.setattr(journal, "has_journalctl", lambda: True)
        monkeypatch.setattr(journal, "has_journal_files", lambda: True)
        assert journal.is_available() is True

    def test_binary_without_a_journal_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(journal, "has_journalctl", lambda: True)
        monkeypatch.setattr(journal, "has_journal_files", lambda: False)
        assert journal.is_available() is False
        assert "no journal exists" in journal.missing_reason()

    def test_absent_binary_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(journal, "has_journalctl", lambda: False)
        assert journal.is_available() is False
        assert "journalctl" in journal.missing_reason()

    def test_no_reason_when_available(self, monkeypatch):
        monkeypatch.setattr(journal, "has_journalctl", lambda: True)
        monkeypatch.setattr(journal, "has_journal_files", lambda: True)
        assert journal.missing_reason() == ""

    def test_empty_journal_directory_does_not_count(self, tmp_path, monkeypatch):
        empty = tmp_path / "journal"
        empty.mkdir()
        monkeypatch.setattr(journal, "JOURNAL_DIRECTORIES", (str(empty),))
        assert journal.has_journal_files() is False

    def test_populated_journal_directory_counts(self, tmp_path, monkeypatch):
        populated = tmp_path / "journal"
        populated.mkdir()
        (populated / "system.journal").write_bytes(b"\x00")
        monkeypatch.setattr(journal, "JOURNAL_DIRECTORIES", (str(populated),))
        assert journal.has_journal_files() is True

    def test_missing_directories_are_ignored(self, monkeypatch):
        monkeypatch.setattr(journal, "JOURNAL_DIRECTORIES", ("/nonexistent/journal",))
        assert journal.has_journal_files() is False

    def test_detection_runs_against_the_real_host(self):
        """Whatever the answer, it must not raise."""
        assert isinstance(journal.is_available(), bool)


class TestPriorityMapping:
    @pytest.mark.parametrize(
        ("priority", "level"),
        [
            (0, Level.CRITICAL),
            (1, Level.CRITICAL),
            (2, Level.CRITICAL),
            (3, Level.ERROR),
            (4, Level.WARNING),
            (5, Level.NOTICE),
            (6, Level.INFO),
            (7, Level.DEBUG),
        ],
    )
    def test_maps_every_syslog_severity(self, priority, level):
        assert journal.PRIORITY_TO_LEVEL[priority] == level

    def test_covers_the_whole_range(self):
        assert set(journal.PRIORITY_TO_LEVEL) == set(range(8))

    def test_fixture_priorities_all_map(self):
        entries = journal.parse_json_stream(load("priorities"))
        assert len(entries) == 8
        assert [e.level for e in entries] == [
            Level.CRITICAL,
            Level.CRITICAL,
            Level.CRITICAL,
            Level.ERROR,
            Level.WARNING,
            Level.NOTICE,
            Level.INFO,
            Level.DEBUG,
        ]


class TestParseJsonLine:
    def test_parses_a_full_record(self):
        entries = journal.parse_json_stream(load("entries"))
        assert len(entries) == 5

        entry = entries[1]
        assert entry.message.startswith("Accepted password for alice")
        assert entry.identifier == "sshd"
        assert entry.pid == "1234"
        assert entry.hostname == "testhost"
        assert entry.unit == "ssh.service"
        assert entry.level == Level.INFO
        assert isinstance(entry.timestamp, datetime)

    def test_timestamps_are_ordered(self):
        entries = journal.parse_json_stream(load("entries"))
        stamps = [e.timestamp for e in entries]
        assert stamps == sorted(stamps)

    def test_realtime_timestamp_is_microseconds(self):
        record = json.dumps({"__REALTIME_TIMESTAMP": "1787000000000000", "MESSAGE": "x"})
        entry = journal.parse_json_line(record)
        assert entry.timestamp == datetime.fromtimestamp(1787000000)

    def test_byte_array_message_is_decoded(self):
        """systemd emits MESSAGE as a byte array when it is not valid UTF-8."""
        entries = journal.parse_json_stream(load("edge_cases"))
        assert any("caf" in e.message for e in entries)

    def test_missing_fields_degrade_to_empty(self):
        entry = journal.parse_json_line(json.dumps({"MESSAGE": "bare"}))
        assert entry is not None
        assert entry.message == "bare"
        assert entry.timestamp is None
        assert entry.level is None
        assert entry.identifier == ""

    def test_blank_lines_are_skipped(self):
        assert journal.parse_json_line("") is None
        assert journal.parse_json_line("   ") is None

    def test_malformed_json_is_skipped_not_raised(self):
        """One bad record must not abort a whole stream."""
        assert journal.parse_json_line("{not valid json") is None

    def test_non_object_records_are_skipped(self):
        assert journal.parse_json_line('["not", "an", "object"]') is None

    def test_stream_skips_bad_records_and_keeps_good_ones(self):
        entries = journal.parse_json_stream(load("edge_cases"))
        # Six lines in, three of which are blank or unparseable.
        assert len(entries) == 3

    def test_garbage_timestamp_is_tolerated(self):
        entry = journal.parse_json_line(
            json.dumps({"__REALTIME_TIMESTAMP": "not-a-number", "MESSAGE": "x"})
        )
        assert entry is not None
        assert entry.timestamp is None

    def test_garbage_priority_is_tolerated(self):
        entry = journal.parse_json_line(json.dumps({"PRIORITY": "high", "MESSAGE": "x"}))
        assert entry is not None
        assert entry.level is None

    def test_falls_back_to_comm_when_identifier_is_absent(self):
        entry = journal.parse_json_line(json.dumps({"MESSAGE": "x", "_COMM": "dockerd"}))
        assert entry.identifier == "dockerd"


class TestJournalEntryFormatting:
    def test_formats_like_short_iso(self):
        entry = journal.parse_json_stream(load("entries"))[1]
        rendered = entry.format()
        assert "testhost" in rendered
        assert "sshd[1234]:" in rendered
        assert "Accepted password for alice" in rendered

    def test_formats_without_a_timestamp(self):
        entry = journal.parse_json_line(json.dumps({"MESSAGE": "bare"}))
        assert entry.format().startswith("- ")

    def test_converts_to_a_log_line(self):
        entry = journal.parse_json_stream(load("entries"))[4]
        line = entry.to_log_line()
        assert isinstance(line, LogLine)
        assert line.level == Level.CRITICAL
        assert "Out of memory" in line.text


class TestDeferredWork:
    """Guards on the TODO, so it cannot quietly look finished."""

    def test_read_is_not_implemented(self):
        with pytest.raises(NotImplementedError, match="not implemented"):
            journal.read()

    def test_follow_is_not_implemented(self):
        with pytest.raises(NotImplementedError, match="not implemented"):
            journal.follow()

    def test_the_todo_points_at_this_module(self):
        assert "TODO" in journal.__doc__
        assert "synthetic" in journal.__doc__
