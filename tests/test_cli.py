"""Tests for argument parsing and validation."""

from __future__ import annotations

import pytest

from sarplot.cli import TAB_CHOICES, build_parser
from sarplot.views.history_view import normalise_time


class TestNormaliseTime:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("", ""),
            ("08:00:00", "08:00:00"),
            ("8:00", "08:00:00"),
            ("08:30", "08:30:00"),
            ("23:59:59", "23:59:59"),
            ("00:00:00", "00:00:00"),
            ("  09:15  ", "09:15:00"),
        ],
    )
    def test_accepts_and_pads_valid_times(self, value, expected):
        assert normalise_time(value) == expected

    @pytest.mark.parametrize(
        "value", ["24:00:00", "12:60:00", "12:00:60", "noon", "12", "12:", "-1:00", "1:2:3:4"]
    )
    def test_rejects_invalid_times(self, value):
        assert normalise_time(value) is None


class TestParser:
    def test_defaults(self):
        args = build_parser().parse_args([])
        assert args.file is None
        assert args.start == ""
        assert args.end == ""
        assert args.refresh == 2.0
        assert args.tab == "processes"

    def test_accepts_all_options(self):
        args = build_parser().parse_args(
            ["-f", "/var/log/sa/sa01", "-s", "08:00", "-e", "10:00", "-r", "5", "-t", "history"]
        )
        assert args.file == "/var/log/sa/sa01"
        assert args.tab == "history"
        assert args.refresh == 5.0

    def test_rejects_an_unknown_tab(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--tab", "nope"])

    def test_tab_choices_map_to_real_pane_ids(self):
        assert set(TAB_CHOICES.values()) == {
            "tab-processes",
            "tab-live",
            "tab-history",
            "tab-system",
        }


class TestMainValidation:
    """main() validates before constructing the app, so these never launch."""

    @staticmethod
    def _run(argv):
        from sarplot.cli import main

        return main(argv)

    def test_rejects_a_non_positive_refresh(self, capsys):
        with pytest.raises(SystemExit):
            self._run(["--refresh", "0"])
        assert "refresh" in capsys.readouterr().err

    def test_rejects_an_invalid_start(self, capsys):
        with pytest.raises(SystemExit):
            self._run(["--start", "25:00"])
        assert "start" in capsys.readouterr().err

    def test_rejects_an_invalid_end(self, capsys):
        with pytest.raises(SystemExit):
            self._run(["--end", "banana"])
        assert "end" in capsys.readouterr().err

    def test_rejects_an_inverted_window(self, capsys):
        with pytest.raises(SystemExit):
            self._run(["--start", "10:00", "--end", "08:00"])
        assert "earlier" in capsys.readouterr().err

    def test_version_exits_cleanly(self, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run(["--version"])
        assert exc.value.code == 0
        assert "sarplot" in capsys.readouterr().out
