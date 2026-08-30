"""Tests for the log file collector."""

from __future__ import annotations

import bz2
import gzip
import lzma
import os
from pathlib import Path

import pytest

from sarplot.collectors import logs


def write_lines(path: Path, count: int, prefix: str = "line") -> Path:
    path.write_text("".join(f"{prefix} {i}\n" for i in range(1, count + 1)))
    return path


class TestTailBytes:
    def test_returns_the_last_n_lines(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 20)
        raw, size = logs.tail_bytes(path, 5)
        assert logs.split_lines(raw) == [f"line {i}" for i in range(16, 21)]
        assert size == path.stat().st_size

    def test_returns_everything_when_fewer_lines_exist(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 3)
        raw, _ = logs.tail_bytes(path, 100)
        assert logs.split_lines(raw) == ["line 1", "line 2", "line 3"]

    def test_handles_a_missing_trailing_newline(self, tmp_path):
        path = tmp_path / "a.log"
        path.write_text("a\nb\nc")
        raw, _ = logs.tail_bytes(path, 5)
        assert logs.split_lines(raw) == ["a", "b", "c"]

    def test_handles_an_empty_file(self, tmp_path):
        path = tmp_path / "a.log"
        path.write_text("")
        raw, size = logs.tail_bytes(path, 5)
        assert raw == b""
        assert size == 0

    def test_handles_a_single_line(self, tmp_path):
        path = tmp_path / "a.log"
        path.write_text("only\n")
        raw, _ = logs.tail_bytes(path, 5)
        assert logs.split_lines(raw) == ["only"]

    def test_spans_block_boundaries(self, tmp_path):
        """The backwards read must stitch blocks together correctly."""
        path = tmp_path / "a.log"
        filler = "x" * (logs.BLOCK_SIZE - 1)
        path.write_text(f"{filler}\nsecond\nthird\n")
        raw, _ = logs.tail_bytes(path, 2)
        assert logs.split_lines(raw) == ["second", "third"]

    def test_reads_across_several_blocks(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 4000)
        raw, _ = logs.tail_bytes(path, 3)
        assert logs.split_lines(raw) == ["line 3998", "line 3999", "line 4000"]

    def test_zero_lines_reads_nothing(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 10)
        raw, size = logs.tail_bytes(path, 0)
        assert raw == b""
        assert size > 0

    def test_does_not_read_the_whole_file(self, tmp_path, monkeypatch):
        """Regression guard: a naive implementation reads everything, which
        stalls the UI on a multi-hundred-megabyte system log.

        The counter wraps the file object rather than patching os.read, which
        buffered I/O bypasses entirely.
        """
        path = write_lines(tmp_path / "big.log", 50_000)
        total = path.stat().st_size
        assert total > 100_000, "fixture must be large enough for this to mean anything"

        tally = {"read": 0}
        real_open = Path.open

        class CountingHandle:
            def __init__(self, handle):
                self._handle = handle

            def read(self, *args):
                data = self._handle.read(*args)
                tally["read"] += len(data)
                return data

            def __getattr__(self, name):
                return getattr(self._handle, name)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return self._handle.__exit__(*exc)

        def counting_open(self, *args, **kwargs):
            return CountingHandle(real_open(self, *args, **kwargs))

        monkeypatch.setattr(Path, "open", counting_open)
        logs.tail_bytes(path, 5)

        assert tally["read"] > 0, "the counter must actually observe the reads"
        assert tally["read"] < total / 10, f"read {tally['read']} of {total} bytes"


class TestDecoding:
    def test_invalid_utf8_is_replaced_not_raised(self, tmp_path):
        path = tmp_path / "a.log"
        path.write_bytes(b"good\n\xff\xfe bad\n")
        source = logs.FileSource(path)
        texts = [line.text for line in source.read_initial(5)]
        assert texts[0] == "good"
        assert "bad" in texts[1]

    def test_crlf_terminators_are_stripped(self, tmp_path):
        path = tmp_path / "a.log"
        path.write_bytes(b"one\r\ntwo\r\n")
        assert logs.split_lines(b"one\r\ntwo\r\n") == ["one", "two"]
        assert [line.text for line in logs.FileSource(path).read_initial(5)] == [
            "one",
            "two",
        ]


class TestDetectLevel:
    @pytest.mark.parametrize(
        ("text", "level"),
        [
            ("something ERROR happened", logs.Level.ERROR),
            ("a WARNING here", logs.Level.WARNING),
            ("CRITICAL failure", logs.Level.CRITICAL),
            ("kernel panic", logs.Level.CRITICAL),
            ("NOTICE: reloaded", logs.Level.NOTICE),
            ("info: unpacking", logs.Level.INFO),
            ("debug trace output", logs.Level.DEBUG),
            ("connection failed", logs.Level.ERROR),
        ],
    )
    def test_recognises_common_keywords(self, text, level):
        assert logs.detect_level(text) == level

    def test_returns_none_for_an_ordinary_line(self):
        assert logs.detect_level("Accepted password for alice from 10.0.0.1") is None

    def test_severity_wins_over_weaker_keywords(self):
        """A line mentioning both must take the more serious one."""
        assert logs.detect_level("INFO: fatal error while starting") == logs.Level.CRITICAL

    def test_matches_whole_words_only(self):
        assert logs.detect_level("reinformed the cluster") is None


class TestLooksBinary:
    def test_text_is_not_binary(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 5)
        assert logs.looks_binary(path) is False

    def test_null_bytes_mean_binary(self, tmp_path):
        path = tmp_path / "a.bin"
        path.write_bytes(b"abc\x00def")
        assert logs.looks_binary(path) is True

    def test_high_nontext_ratio_means_binary(self, tmp_path):
        path = tmp_path / "a.bin"
        path.write_bytes(bytes(range(1, 32)) * 40)
        assert logs.looks_binary(path) is True

    def test_empty_file_is_not_binary(self, tmp_path):
        path = tmp_path / "a.log"
        path.write_bytes(b"")
        assert logs.looks_binary(path) is False

    @pytest.mark.parametrize("name", ["wtmp", "btmp", "lastlog", "utmp", "wtmp.1"])
    def test_known_binary_logs_are_rejected_by_name(self, tmp_path, name):
        """These hold fixed-width C structs. An empty one passes a content
        probe, so the name has to be checked too."""
        path = tmp_path / name
        path.write_bytes(b"")
        assert logs.looks_binary(path) is True

    def test_unreadable_file_raises_log_error(self, tmp_path):
        path = tmp_path / "secret.log"
        path.write_text("hidden\n")
        path.chmod(0o000)
        try:
            if os.geteuid() == 0:
                pytest.skip("root bypasses file permissions")
            with pytest.raises(logs.LogError, match="Permission denied"):
                logs.looks_binary(path)
        finally:
            path.chmod(0o644)


class TestCompressed:
    @pytest.mark.parametrize(("suffix", "module"), [(".gz", gzip), (".xz", lzma), (".bz2", bz2)])
    def test_reads_rotated_archives(self, tmp_path, suffix, module):
        path = tmp_path / f"old.log{suffix}"
        with module.open(path, "wb") as handle:
            handle.write(b"".join(f"c{i}\n".encode() for i in range(1, 11)))

        source = logs.FileSource(path)
        assert [line.text for line in source.read_initial(3)] == ["c8", "c9", "c10"]

    @pytest.mark.parametrize("suffix", [".gz", ".xz", ".bz2"])
    def test_compressed_archives_are_not_followable(self, tmp_path, suffix):
        """A rotated archive is a fixed snapshot; nothing will be appended."""
        path = tmp_path / f"old.log{suffix}"
        path.write_bytes(b"")
        source = logs.FileSource(path)
        assert source.followable is False
        assert source.read_new() == []

    def test_is_compressed_detects_suffixes(self, tmp_path):
        assert logs.is_compressed(Path("a.log.gz")) is True
        assert logs.is_compressed(Path("a.log")) is False

    def test_corrupt_archive_raises_log_error(self, tmp_path):
        path = tmp_path / "broken.log.gz"
        path.write_bytes(b"this is not gzip data at all")
        with pytest.raises(logs.LogError):
            logs.FileSource(path).read_initial(5)


class TestFileSourceFollow:
    def test_initial_read_then_appends(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 5)
        source = logs.FileSource(path)

        assert [line.text for line in source.read_initial(3)] == [
            "line 3",
            "line 4",
            "line 5",
        ]

        with path.open("a") as handle:
            handle.write("line 6\nline 7\n")

        assert [line.text for line in source.read_new()] == ["line 6", "line 7"]

    def test_no_change_yields_nothing(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 5)
        source = logs.FileSource(path)
        source.read_initial(3)
        assert source.read_new() == []
        assert source.read_new() == []

    def test_partial_line_is_picked_up_once_complete(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 2)
        source = logs.FileSource(path)
        source.read_initial(5)

        with path.open("a") as handle:
            handle.write("incomplete")
        first = [line.text for line in source.read_new()]

        with path.open("a") as handle:
            handle.write(" now complete\n")
        second = [line.text for line in source.read_new()]

        assert "".join(first + second) == "incomplete now complete"

    def test_detects_truncation_in_place(self, tmp_path):
        """logrotate copytruncate, or a plain `> logfile`."""
        path = write_lines(tmp_path / "a.log", 20)
        source = logs.FileSource(path)
        source.read_initial(5)

        path.write_text("fresh 1\nfresh 2\n")
        assert [line.text for line in source.read_new()] == ["fresh 1", "fresh 2"]
        assert source.rotated_since_last_read is True

    def test_detects_rotation_to_a_new_inode(self, tmp_path):
        """logrotate's default: rename the old file, create a new one."""
        path = write_lines(tmp_path / "a.log", 20)
        source = logs.FileSource(path)
        source.read_initial(5)
        original_inode = path.stat().st_ino

        os.rename(path, tmp_path / "a.log.1")
        path.write_text("rotated 1\nrotated 2\n")
        assert path.stat().st_ino != original_inode

        assert [line.text for line in source.read_new()] == ["rotated 1", "rotated 2"]
        assert source.rotated_since_last_read is True

    def test_rotation_flag_resets_after_a_quiet_read(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 5)
        source = logs.FileSource(path)
        source.read_initial(5)
        path.write_text("new\n")
        source.read_new()
        assert source.rotated_since_last_read is True
        source.read_new()
        assert source.rotated_since_last_read is False

    def test_binary_file_is_refused(self, tmp_path):
        path = tmp_path / "a.bin"
        path.write_bytes(b"\x00\x01binary\x00")
        with pytest.raises(logs.LogError, match="binary"):
            logs.FileSource(path).read_initial(5)

    def test_missing_file_raises_log_error(self, tmp_path):
        source = logs.FileSource(tmp_path / "gone.log")
        with pytest.raises(logs.LogError):
            source.read_initial(5)

    def test_file_deleted_while_following_raises_log_error(self, tmp_path):
        path = write_lines(tmp_path / "a.log", 5)
        source = logs.FileSource(path)
        source.read_initial(5)
        path.unlink()
        with pytest.raises(logs.LogError, match="no longer exists"):
            source.read_new()

    def test_levels_are_attached_to_lines(self, tmp_path):
        path = tmp_path / "a.log"
        path.write_text("plain line\nsomething ERROR here\n")
        lines = logs.FileSource(path).read_initial(5)
        assert lines[1].level == logs.Level.ERROR

    def test_satisfies_the_log_source_protocol(self, tmp_path):
        """The seam a journald source will implement later."""
        path = write_lines(tmp_path / "a.log", 2)
        assert isinstance(logs.FileSource(path), logs.LogSource)


class TestDiscovery:
    def test_prefers_the_first_existing_candidate(self, tmp_path):
        second = tmp_path / "messages"
        second.write_text("hi\n")
        found = logs.discover_system_log([str(tmp_path / "syslog"), str(second)])
        assert found == second

    def test_returns_none_when_no_candidate_exists(self, tmp_path):
        assert logs.discover_system_log([str(tmp_path / "nope")]) is None

    def test_skips_unreadable_candidates(self, tmp_path):
        if os.geteuid() == 0:
            pytest.skip("root bypasses file permissions")
        blocked = tmp_path / "syslog"
        blocked.write_text("x\n")
        blocked.chmod(0o000)
        readable = tmp_path / "messages"
        readable.write_text("y\n")
        try:
            assert logs.discover_system_log([str(blocked), str(readable)]) == readable
        finally:
            blocked.chmod(0o644)

    def test_lists_only_readable_text_logs(self, tmp_path):
        write_lines(tmp_path / "good.log", 3)
        (tmp_path / "binary.log").write_bytes(b"\x00\x01\x02")
        (tmp_path / "wtmp").write_bytes(b"")
        (tmp_path / "subdir").mkdir()

        names = {p.name for p in logs.list_readable_logs(tmp_path)}
        assert names == {"good.log"}

    def test_missing_directory_yields_nothing(self, tmp_path):
        assert logs.list_readable_logs(tmp_path / "nope") == []

    def test_default_falls_back_to_newest_readable_file(self, tmp_path, monkeypatch):
        """On systemd-only hosts there is no syslog file at all."""
        monkeypatch.setattr(logs, "SYSTEM_LOG_CANDIDATES", ())
        old = write_lines(tmp_path / "old.log", 3)
        new = write_lines(tmp_path / "new.log", 3)
        os.utime(old, (1_000_000, 1_000_000))
        os.utime(new, (2_000_000, 2_000_000))

        assert logs.default_log(tmp_path) == new

    def test_default_ignores_rotated_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "SYSTEM_LOG_CANDIDATES", ())
        current = write_lines(tmp_path / "app.log", 3)
        rotated = write_lines(tmp_path / "app.log.1", 3)
        os.utime(current, (1_000_000, 1_000_000))
        os.utime(rotated, (9_000_000, 9_000_000))

        assert logs.default_log(tmp_path) == current

    def test_default_returns_none_when_nothing_is_readable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "SYSTEM_LOG_CANDIDATES", ())
        assert logs.default_log(tmp_path) is None

    @pytest.mark.parametrize(
        ("name", "rotated"),
        [
            ("syslog", False),
            ("app.log", False),
            ("syslog.1", True),
            ("syslog.2.gz", True),
            ("messages.10.xz", True),
        ],
    )
    def test_rotated_names_are_recognised(self, name, rotated):
        assert logs.is_rotated_name(Path(name)) is rotated


class TestLevelStyleResolution:
    """Rich cannot parse Textual's '$variable' syntax.

    Passing '$text-error' straight to Text() silently produces no styling at
    all, so theme variables have to be resolved to real colours first.
    """

    def test_resolves_colours_from_theme_variables(self):
        from sarplot.views.log_view import resolve_level_styles

        resolved = resolve_level_styles(
            {"text-error": "#D17E92", "text-warning": "#FFC473", "text-accent": "#88C0D0"}
        )
        assert resolved[logs.Level.ERROR] == "#D17E92"
        assert resolved[logs.Level.WARNING] == "#FFC473"
        assert resolved[logs.Level.CRITICAL] == "bold #D17E92"

    def test_every_level_resolves_to_a_parseable_rich_style(self):
        from rich.style import Style

        from sarplot.views.log_view import resolve_level_styles

        resolved = resolve_level_styles({"text-error": "#D17E92"})
        for level, style in resolved.items():
            Style.parse(style)  # must not raise
            assert isinstance(style, str), level

    def test_non_colour_theme_values_fall_back(self):
        """`text-muted` is 'auto 60%', which Rich rejects."""
        from rich.style import Style

        from sarplot.views.log_view import resolve_level_styles

        resolved = resolve_level_styles({"text-error": "auto 60%"})
        Style.parse(resolved[logs.Level.ERROR])
        assert "auto" not in resolved[logs.Level.ERROR]

    def test_missing_variables_fall_back_to_named_colours(self):
        from sarplot.views.log_view import LEVEL_FALLBACKS, resolve_level_styles

        resolved = resolve_level_styles({})
        assert resolved[logs.Level.ERROR] == LEVEL_FALLBACKS[logs.Level.ERROR]
        assert resolved[logs.Level.CRITICAL] == LEVEL_FALLBACKS[logs.Level.CRITICAL]

    def test_covers_every_level(self):
        from sarplot.views.log_view import resolve_level_styles

        assert set(resolve_level_styles({})) == set(logs.Level)
