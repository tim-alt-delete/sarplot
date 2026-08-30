"""Tests for the sar collector.

Fixtures under tests/fixtures/ are real `sadf -j` output captured from
sysstat 12.7.7, not hand-written approximations of the schema.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime

import pytest

from sarplot.collectors import sar

from .conftest import load_fixture


class TestParseShapes:
    """Each sar flag produces a different JSON shape; all must flatten."""

    def test_list_of_records_is_keyed_by_identity(self):
        series = sar.parse(load_fixture("cpu"))
        assert "all/user" in series.columns
        assert "all/idle" in series.columns
        assert len(series.timestamps) == 4

    def test_flat_dict_uses_bare_field_names(self):
        series = sar.parse(load_fixture("memory"))
        assert "memused" in series.columns
        assert "memused-percent" in series.columns

    def test_nested_dicts_are_dotted(self):
        series = sar.parse(load_fixture("io"))
        assert "tps" in series.columns
        assert "io-reads.rtps" in series.columns
        assert "io-writes.bwrtn" in series.columns

    def test_nested_list_drops_the_container_name(self):
        """network -> net-dev -> [{iface: eth0, ...}] should read 'eth0/rxkB'."""
        series = sar.parse(load_fixture("network"))
        assert "eth0/rxkB" in series.columns
        assert not any(name.startswith("net-dev") for name in series.names)

    def test_per_core_cpu_yields_one_group_per_core(self):
        series = sar.parse(load_fixture("cpu_per_core"))
        assert "all/user" in series.columns
        assert "0/user" in series.columns
        assert "9/user" in series.columns

    def test_disk_is_keyed_by_device(self):
        series = sar.parse(load_fixture("disk"))
        assert any(name.endswith("/tps") for name in series.names)
        assert "vda/util-percent" in series.columns

    @pytest.mark.parametrize(
        "name", ["cpu", "memory", "swap", "queue", "io", "network", "paging", "disk"]
    )
    def test_every_metric_parses_to_aligned_columns(self, name):
        series = sar.parse(load_fixture(name))
        assert series
        for column in series.columns.values():
            assert len(column) == len(series.timestamps)


class TestDerivedSeries:
    def test_busy_is_derived_from_idle(self):
        series = sar.parse(load_fixture("cpu"))
        assert "all/busy" in series.columns
        idle = series.columns["all/idle"]
        busy = series.columns["all/busy"]
        for i, b in zip(idle, busy, strict=True):
            assert b == pytest.approx(100.0 - i)


class TestTimestamps:
    def test_timestamps_are_parsed_in_order(self):
        series = sar.parse(load_fixture("cpu"))
        assert all(isinstance(t, datetime) for t in series.timestamps)
        assert series.timestamps == sorted(series.timestamps)

    def test_legacy_utc_key_is_accepted(self):
        """sysstat < 12.7 emitted 'utc' where 12.7+ emits 'tz'.

        Neither is needed to place a sample on a time axis, so both parse.
        """
        modern = sar.parse(load_fixture("cpu"))
        legacy = sar.parse(load_fixture("cpu_legacy_utc"))
        assert legacy.timestamps == modern.timestamps
        assert legacy.columns.keys() == modern.columns.keys()


class TestEdgeCases:
    def test_empty_statistics_entries_are_skipped(self):
        """sadf pads the array with {} around restarts and file boundaries."""
        raw = json.loads(load_fixture("cpu_with_empty_entries"))
        assert {} in raw["sysstat"]["hosts"][0]["statistics"]

        series = sar.parse(load_fixture("cpu_with_empty_entries"))
        assert len(series.timestamps) == 2
        assert all(len(c) == 2 for c in series.columns.values())

    def test_no_samples_is_falsy_rather_than_an_error(self):
        series = sar.parse(load_fixture("no_data"))
        assert not series
        assert series.timestamps == []

    def test_malformed_json_raises_sar_error(self):
        with pytest.raises(sar.SarError, match="malformed JSON"):
            sar.parse("{not json")

    def test_missing_sysstat_key_raises_sar_error(self):
        with pytest.raises(sar.SarError, match=r"sysstat\.hosts"):
            sar.parse(json.dumps({"something": "else"}))

    def test_no_hosts_returns_empty_series(self):
        assert not sar.parse(json.dumps({"sysstat": {"hosts": []}}))

    def test_nodename_is_captured(self):
        assert sar.parse(load_fixture("cpu")).nodename == "testhost"


class TestSparseSeries:
    """A device can appear part-way through an archive."""

    @staticmethod
    def _sparse() -> sar.TimeSeries:
        series = sar.TimeSeries()
        series.timestamps = [datetime(2026, 8, 30, 10, i) for i in range(4)]
        series.columns = {"late/tps": [None, None, 5.0, 7.0]}
        return series

    def test_points_drops_gaps(self):
        stamps, values = self._sparse().points("late/tps")
        assert values == [5.0, 7.0]
        assert stamps == [datetime(2026, 8, 30, 10, 2), datetime(2026, 8, 30, 10, 3)]

    def test_indexed_preserves_true_positions(self):
        """Regression: plotting against range(len(values)) shifted sparse
        series to the left, misaligning them with the shared time axis."""
        positions, values = self._sparse().indexed("late/tps")
        assert positions == [2, 3]
        assert values == [5.0, 7.0]

    def test_unknown_series_is_empty_not_an_error(self):
        assert self._sparse().points("nope") == ([], [])
        assert self._sparse().indexed("nope") == ([], [])

    def test_columns_backfill_when_a_device_appears_late(self):
        document = {
            "sysstat": {
                "hosts": [
                    {
                        "nodename": "h",
                        "statistics": [
                            {
                                "timestamp": {"date": "2026-08-30", "time": "10:00:00"},
                                "disk": [{"disk-device": "sda", "tps": 1.0}],
                            },
                            {
                                "timestamp": {"date": "2026-08-30", "time": "10:01:00"},
                                "disk": [
                                    {"disk-device": "sda", "tps": 2.0},
                                    {"disk-device": "sdb", "tps": 9.0},
                                ],
                            },
                        ],
                    }
                ]
            }
        }
        series = sar.parse(json.dumps(document))
        assert series.columns["sda/tps"] == [1.0, 2.0]
        # sdb was absent from the first sample and is back-filled with None.
        assert series.columns["sdb/tps"] == [None, 9.0]


class TestChooseDefaultSeries:
    def test_exact_matches_beat_substring_matches(self):
        """'tps' must pick the aggregate, not 'io-discard.dtps'."""
        series = sar.parse(load_fixture("io"))
        chosen = sar.choose_default_series(series, sar.METRICS_BY_KEY["io"])
        assert chosen[0] == "tps"

    def test_ldavg_1_does_not_swallow_ldavg_15(self):
        series = sar.parse(load_fixture("queue"))
        chosen = sar.choose_default_series(series, sar.METRICS_BY_KEY["load"])
        assert chosen[:3] == ["ldavg-1", "ldavg-5", "ldavg-15"]

    def test_cpu_prefers_the_aggregate_breakdown(self):
        series = sar.parse(load_fixture("cpu"))
        chosen = sar.choose_default_series(series, sar.METRICS_BY_KEY["cpu"])
        assert chosen[0] == "all/busy"

    def test_respects_the_limit(self):
        series = sar.parse(load_fixture("cpu_per_core"))
        chosen = sar.choose_default_series(series, sar.METRICS_BY_KEY["cpu-per-core"], limit=3)
        assert len(chosen) == 3

    @pytest.mark.parametrize(
        ("fixture", "metric"),
        [
            ("cpu", "cpu"),
            ("cpu_per_core", "cpu-per-core"),
            ("memory", "memory"),
            ("swap", "swap"),
            ("queue", "load"),
            ("io", "io"),
            ("network", "network"),
            ("disk", "disk"),
            ("paging", "paging"),
        ],
    )
    def test_defaults_never_mix_percentages_with_absolute_values(self, fixture, metric):
        """A percentage plotted beside kB values is flattened to a flat line
        against a multi-million-unit axis."""
        series = sar.parse(load_fixture(fixture))
        chosen = sar.choose_default_series(series, sar.METRICS_BY_KEY[metric])
        percentages = [name for name in chosen if "percent" in name]
        assert not percentages or len(percentages) == len(chosen), chosen

    def test_memory_defaults_to_absolute_series(self):
        series = sar.parse(load_fixture("memory"))
        chosen = sar.choose_default_series(series, sar.METRICS_BY_KEY["memory"])
        assert chosen == ["memused", "avail", "cached", "buffers"]

    def test_stops_once_every_pattern_has_matched(self):
        """Otherwise a looser tier pads the list with near-duplicates."""
        series = sar.parse(load_fixture("swap"))
        chosen = sar.choose_default_series(series, sar.METRICS_BY_KEY["swap"])
        assert "swpused-percent" not in chosen

    def test_falls_back_when_nothing_matches(self):
        series = sar.parse(load_fixture("cpu"))
        spec = sar.MetricSpec("x", "X", ("-u",), preferred=("nonexistent",))
        assert sar.choose_default_series(series, spec) == series.names[:4]

    def test_empty_series_yields_no_selection(self):
        assert sar.choose_default_series(sar.TimeSeries(), sar.METRICS[0]) == []


class TestQuery:
    def test_missing_archive_raises_before_invoking_sadf(self, tmp_path):
        with pytest.raises(sar.SarError, match="Archive not found"):
            sar.query(tmp_path / "sa99", sar.METRICS[0])

    def test_absent_sadf_raises_sar_unavailable(self, tmp_path, monkeypatch):
        archive = tmp_path / "sa01"
        archive.write_bytes(b"")

        def boom(*args, **kwargs):
            raise FileNotFoundError(2, "No such file or directory")

        monkeypatch.setattr(subprocess, "run", boom)
        with pytest.raises(sar.SarUnavailable):
            sar.query(archive, sar.METRICS[0], use_cache=False)

    def test_sadf_failure_surfaces_stderr(self, tmp_path, monkeypatch):
        archive = tmp_path / "sa01"
        archive.write_bytes(b"")

        def boom(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "sadf", stderr="Invalid system activity file")

        monkeypatch.setattr(subprocess, "run", boom)
        with pytest.raises(sar.SarError, match="Invalid system activity file"):
            sar.query(archive, sar.METRICS[0], use_cache=False)

    def test_timeout_is_reported_clearly(self, tmp_path, monkeypatch):
        archive = tmp_path / "sa01"
        archive.write_bytes(b"")

        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired("sadf", sar.SADF_TIMEOUT_SECONDS)

        monkeypatch.setattr(subprocess, "run", boom)
        with pytest.raises(sar.SarError, match="timed out"):
            sar.query(archive, sar.METRICS[0], use_cache=False)

    def test_time_window_is_passed_through_to_sadf(self, tmp_path, monkeypatch):
        archive = tmp_path / "sa01"
        archive.write_bytes(b"")
        seen: dict = {}

        class Result:
            stdout = load_fixture("cpu")

        def fake_run(command, **kwargs):
            seen["command"] = command
            return Result()

        monkeypatch.setattr(subprocess, "run", fake_run)
        sar.query(archive, sar.METRICS_BY_KEY["cpu"], "08:00:00", "10:30:00", use_cache=False)

        command = seen["command"]
        assert command[:2] == ["sadf", "-j"]
        assert "-u" in command
        assert command[command.index("-s") + 1] == "08:00:00"
        assert command[command.index("-e") + 1] == "10:30:00"

    def test_empty_window_omits_the_flags(self, tmp_path, monkeypatch):
        archive = tmp_path / "sa01"
        archive.write_bytes(b"")
        seen: dict = {}

        class Result:
            stdout = load_fixture("cpu")

        monkeypatch.setattr(
            subprocess, "run", lambda command, **kw: (seen.update(command=command), Result())[1]
        )
        sar.query(archive, sar.METRICS_BY_KEY["cpu"], use_cache=False)
        assert "-s" not in seen["command"]
        assert "-e" not in seen["command"]


class TestArchiveDiscovery:
    def test_recognises_both_naming_schemes(self, tmp_path, monkeypatch):
        (tmp_path / "sa05").write_bytes(b"")
        (tmp_path / "sa20260830").write_bytes(b"")
        (tmp_path / "sar05").write_bytes(b"")  # text report, not an archive
        (tmp_path / "notes.txt").write_bytes(b"")

        monkeypatch.setattr(sar, "LOG_DIRECTORIES", (str(tmp_path),))
        names = {f.path.name for f in sar.list_log_files()}
        assert names == {"sa05", "sa20260830"}

    def test_dated_filename_is_parsed(self, tmp_path, monkeypatch):
        (tmp_path / "sa20260830").write_bytes(b"")
        monkeypatch.setattr(sar, "LOG_DIRECTORIES", (str(tmp_path),))
        found = sar.list_log_files()[0]
        assert found.day == datetime(2026, 8, 30).date()
        assert "2026-08-30" in found.label

    def test_missing_directories_are_ignored(self, monkeypatch):
        monkeypatch.setattr(sar, "LOG_DIRECTORIES", ("/nonexistent/a", "/nonexistent/b"))
        assert sar.list_log_files() == []
        assert sar.is_available() is False

    def test_missing_reason_mentions_sysstat_when_sadf_absent(self, monkeypatch):
        monkeypatch.setattr(sar.shutil, "which", lambda _: None)
        assert "sysstat" in sar.missing_reason()

    def test_missing_reason_lists_directories_when_sadf_present(self, monkeypatch):
        monkeypatch.setattr(sar.shutil, "which", lambda _: "/usr/bin/sadf")
        monkeypatch.setattr(sar, "LOG_DIRECTORIES", ("/var/log/sysstat",))
        assert "/var/log/sysstat" in sar.missing_reason()


class TestMetricRegistry:
    def test_keys_are_unique(self):
        keys = [m.key for m in sar.METRICS]
        assert len(keys) == len(set(keys))

    def test_lookup_matches_the_tuple(self):
        assert set(sar.METRICS_BY_KEY) == {m.key for m in sar.METRICS}

    def test_percentage_metrics_clamp_the_axis(self):
        assert sar.METRICS_BY_KEY["cpu"].ylim == (0, 100)
