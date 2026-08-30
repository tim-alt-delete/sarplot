"""Browse, tail and search log files."""

from __future__ import annotations

import os
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Checkbox, DirectoryTree, Input, RichLog, Static

from sarplot.collectors import journal, logs

#: How often to check a followed file for new content. Polling with stat() is
#: enough at this cadence and avoids taking on an inotify dependency.
POLL_SECONDS = 0.5

#: Lines retained in memory. Bounds both the ring buffer and the RichLog.
DEFAULT_MAX_LINES = 5000

#: Style per severity, resolved against the active Textual theme.
LEVEL_STYLES: dict[logs.Level, str] = {
    logs.Level.CRITICAL: "bold $text-error",
    logs.Level.ERROR: "$text-error",
    logs.Level.WARNING: "$text-warning",
    logs.Level.NOTICE: "$text-accent",
    logs.Level.INFO: "",
    logs.Level.DEBUG: "$text-muted",
}


@dataclass
class Query:
    """A compiled search, or the absence of one."""

    text: str = ""
    regex: bool = False
    case_sensitive: bool = False
    pattern: re.Pattern[str] | None = None
    error: str = ""

    @property
    def active(self) -> bool:
        return self.pattern is not None

    def matches(self, line: str) -> bool:
        return self.pattern is not None and self.pattern.search(line) is not None

    def spans(self, line: str) -> list[tuple[int, int]]:
        if self.pattern is None:
            return []
        return [m.span() for m in self.pattern.finditer(line) if m.end() > m.start()]


def compile_query(text: str, *, regex: bool, case_sensitive: bool) -> Query:
    """Build a Query, reporting a bad pattern instead of raising.

    An invalid regex is a normal thing to type halfway through entering one,
    so it is reported inline rather than propagating.
    """
    if not text:
        return Query(text="", regex=regex, case_sensitive=case_sensitive)

    flags = 0 if case_sensitive else re.IGNORECASE
    source = text if regex else re.escape(text)
    try:
        pattern = re.compile(source, flags)
    except re.error as exc:
        return Query(
            text=text,
            regex=regex,
            case_sensitive=case_sensitive,
            error=f"Invalid regular expression: {exc}",
        )
    return Query(
        text=text,
        regex=regex,
        case_sensitive=case_sensitive,
        pattern=pattern,
    )


class LogDirectoryTree(DirectoryTree):
    """A directory tree showing only files worth opening as logs."""

    def filter_paths(self, paths):
        keep = []
        for path in paths:
            if path.name.startswith("."):
                continue
            if path.is_dir():
                # An unreadable directory expands to nothing with no
                # explanation, so hide it rather than offering a dead end.
                if os.access(path, os.R_OK | os.X_OK):
                    keep.append(path)
                continue
            if not logs.is_readable(path):
                # Unreadable files are hidden rather than offered and then
                # refused; most of /var/log needs root.
                continue
            try:
                if logs.looks_binary(path):
                    continue
            except logs.LogError:
                continue
            keep.append(path)
        return keep


class LogView(Horizontal):
    """A file explorer beside a tailing, searchable log pane."""

    BINDINGS = [
        Binding("slash", "focus_search", "Search"),
        Binding("f", "toggle_follow", "Follow"),
        Binding("h", "toggle_mode", "Filter/Highlight"),
        Binding("r", "toggle_regex", "Regex"),
        Binding("a", "toggle_case", "Case"),
        Binding("n", "next_match", "Next match"),
        Binding("N", "previous_match", "Prev match"),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False),
        Binding("ctrl+l", "clear", "Clear", show=False),
        Binding("escape", "clear_search", "Clear search", show=False),
    ]

    def __init__(
        self,
        *,
        log_file: str | None = None,
        log_dir: str = logs.DEFAULT_LOG_DIR,
        max_lines: int = DEFAULT_MAX_LINES,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._log_dir = log_dir
        self._initial_file = log_file
        self._max_lines = max_lines
        self._buffer: deque[logs.LogLine] = deque(maxlen=max_lines)
        self._source: logs.FileSource | None = None
        self._query = Query()
        self._follow = True
        self._filter_mode = True
        self._timer = None
        self._error = ""
        self._match_offsets: list[int] = []
        self._match_index = -1

    # --------------------------------------------------------------- compose

    def compose(self) -> ComposeResult:
        root = Path(self._log_dir)
        with Vertical(id="log-sidebar"):
            if root.is_dir():
                yield LogDirectoryTree(root, id="log-tree")
            else:
                yield Static(
                    f"{root} is not a directory.",
                    id="log-tree-missing",
                )

        with Vertical(id="log-main"):
            with Horizontal(id="log-controls"):
                yield Input(placeholder="Search...", id="log-search")
                yield Checkbox("Regex", value=False, id="log-regex")
                yield Checkbox("Case", value=False, id="log-case")
                yield Checkbox("Filter", value=True, id="log-filter-mode")
                yield Checkbox("Follow", value=True, id="log-follow")
            yield RichLog(
                max_lines=self._max_lines,
                wrap=False,
                markup=False,
                highlight=False,
                auto_scroll=False,
                id="log-output",
            )
            yield Static("", id="log-status")

    def on_mount(self) -> None:
        self.query_one("#log-main").border_title = "No log open"
        sidebar = self.query_one("#log-sidebar")
        sidebar.border_title = self._log_dir

        self._timer = self.set_interval(POLL_SECONDS, self._poll)

        initial = self._resolve_initial_file()
        if initial is not None:
            self.open_path(initial)
        else:
            self._show_empty_state()

    def _resolve_initial_file(self) -> Path | None:
        if self._initial_file:
            return Path(self._initial_file)
        return logs.default_log(self._log_dir)

    # ------------------------------------------------------------- lifecycle

    def pause(self) -> None:
        """Stop polling while the tab is hidden."""
        if self._timer is not None:
            self._timer.pause()

    def resume(self) -> None:
        if self._timer is not None:
            self._timer.resume()

    # ------------------------------------------------------------ log source

    def open_path(self, path: Path) -> None:
        """Open a file, replacing whatever was being tailed."""
        self._buffer.clear()
        self._error = ""
        self._match_index = -1
        source = logs.FileSource(path)

        try:
            initial = source.read_initial(self._max_lines)
        except logs.LogError as exc:
            self._source = None
            self._error = str(exc)
            self.query_one("#log-main").border_title = str(path)
            self._redraw()
            return

        self._source = source
        self._buffer.extend(initial)
        self.query_one("#log-main").border_title = str(path)
        self._redraw()
        self._scroll_to_end()

    def reload_log(self) -> None:
        """Re-read the current file from scratch, for the refresh binding."""
        if self._source is not None:
            self.open_path(self._source.path)

    def _show_empty_state(self) -> None:
        """Explain why nothing opened.

        On a systemd-only host there is no classic syslog file at all, which
        is worth saying explicitly rather than showing a blank pane.
        """
        if journal.is_available():
            self._error = (
                "No classic syslog file was found. This host logs to the "
                "systemd journal, which sarplot cannot read yet - support is "
                "planned. Pick a file on the left to tail it in the meantime."
            )
        else:
            self._error = (
                f"No readable log files were found in {self._log_dir}. "
                "Most system logs require root."
            )
        self._redraw()

    def _poll(self) -> None:
        """Pick up anything appended since the last tick."""
        if self._source is None or not self._follow:
            return

        try:
            new_lines = self._source.read_new()
        except logs.LogError as exc:
            self._error = str(exc)
            self._source = None
            self._redraw()
            return

        if self._source.rotated_since_last_read:
            # The file we were tailing was rotated or truncated; the retained
            # lines belong to a file that no longer exists at this path.
            self._buffer.clear()
            self.notify(f"{self._source.path.name} was rotated; reloaded.")

        if not new_lines:
            return

        self._buffer.extend(new_lines)
        self._redraw()
        self._scroll_to_end()

    # ---------------------------------------------------------------- events

    @on(DirectoryTree.FileSelected, "#log-tree")
    def _on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.open_path(event.path)

    @on(Input.Changed, "#log-search")
    def _on_search_changed(self, event: Input.Changed) -> None:
        self._recompile(event.value)

    @on(Checkbox.Changed, "#log-regex")
    def _on_regex_toggled(self, event: Checkbox.Changed) -> None:
        self._query.regex = bool(event.value)
        self._recompile(self._query.text)

    @on(Checkbox.Changed, "#log-case")
    def _on_case_toggled(self, event: Checkbox.Changed) -> None:
        self._query.case_sensitive = bool(event.value)
        self._recompile(self._query.text)

    @on(Checkbox.Changed, "#log-filter-mode")
    def _on_mode_toggled(self, event: Checkbox.Changed) -> None:
        self._filter_mode = bool(event.value)
        self._redraw()

    @on(Checkbox.Changed, "#log-follow")
    def _on_follow_toggled(self, event: Checkbox.Changed) -> None:
        self._follow = bool(event.value)
        if self._follow:
            self._scroll_to_end()
        self._update_status()

    def _recompile(self, text: str) -> None:
        previous = self._query
        query = compile_query(
            text,
            regex=previous.regex,
            case_sensitive=previous.case_sensitive,
        )
        if query.error:
            # Keep showing the last good result while the pattern is still
            # half-typed, and report the problem in the status line.
            self._query = Query(
                text=text,
                regex=previous.regex,
                case_sensitive=previous.case_sensitive,
                pattern=previous.pattern,
                error=query.error,
            )
            self._update_status()
            return

        self._query = query
        self._match_index = -1
        self._redraw()

    # --------------------------------------------------------------- actions

    def action_focus_search(self) -> None:
        self.query_one("#log-search", Input).focus()

    def action_clear_search(self) -> None:
        self.query_one("#log-search", Input).value = ""

    def action_toggle_follow(self) -> None:
        self.query_one("#log-follow", Checkbox).toggle()

    def action_toggle_mode(self) -> None:
        self.query_one("#log-filter-mode", Checkbox).toggle()

    def action_toggle_regex(self) -> None:
        self.query_one("#log-regex", Checkbox).toggle()

    def action_toggle_case(self) -> None:
        self.query_one("#log-case", Checkbox).toggle()

    def action_scroll_top(self) -> None:
        self.query_one("#log-output", RichLog).scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        self._scroll_to_end()

    def action_clear(self) -> None:
        self._buffer.clear()
        self._redraw()

    def action_next_match(self) -> None:
        self._jump(1)

    def action_previous_match(self) -> None:
        self._jump(-1)

    def _jump(self, direction: int) -> None:
        """Move between matches in highlight mode.

        In filter mode every visible line already matches, so jumping is
        meaningless.
        """
        if not self._match_offsets:
            return

        if self._match_index < 0:
            # Nothing selected yet: forwards starts at the first match,
            # backwards at the last, rather than falling out of the modulo
            # two short of the end.
            self._match_index = 0 if direction > 0 else len(self._match_offsets) - 1
        else:
            self._match_index = (self._match_index + direction) % len(self._match_offsets)

        output = self.query_one("#log-output", RichLog)
        output.scroll_to(y=self._match_offsets[self._match_index], animate=False)
        self._update_status()

    # ---------------------------------------------------------------- render

    def _visible_lines(self) -> list[logs.LogLine]:
        if self._filter_mode and self._query.active:
            return [line for line in self._buffer if self._query.matches(line.text)]
        return list(self._buffer)

    def _style_line(self, line: logs.LogLine) -> Text:
        """Build a styled Text for one log line.

        Deliberately a Text object rather than a markup string: RichLog with
        markup enabled would parse square brackets, and syslog's canonical
        `program[pid]:` format would be silently swallowed as markup tags.
        """
        style = LEVEL_STYLES.get(line.level, "") if line.level else ""
        text = Text(line.text, style=style, no_wrap=True, end="")

        for start, end in self._query.spans(line.text):
            text.stylize("reverse", start, end)
        return text

    def _redraw(self) -> None:
        """Redraw the pane from the retained buffer.

        Cheap enough to do wholesale (a few milliseconds for the full buffer),
        which keeps filtering and mode switching simple and correct.
        """
        output = self.query_one("#log-output", RichLog)
        output.clear()
        self._match_offsets = []

        if self._error:
            output.write(Text(self._error, style="$text-warning"))
            self._update_status()
            return

        for line in self._visible_lines():
            # Record where this line lands so `n`/`N` can scroll to it. Taken
            # before the write because one logical line may render as several
            # strips when wrapping is on.
            if self._query.active and self._query.matches(line.text):
                self._match_offsets.append(len(output.lines))
            output.write(self._style_line(line))

        self._update_status()

    def _scroll_to_end(self) -> None:
        if self._follow:
            self.query_one("#log-output", RichLog).scroll_end(animate=False)

    def _update_status(self) -> None:
        status = self.query_one("#log-status", Static)

        if self._query.error:
            status.update(self._query.error)
            status.set_class(True, "-error")
            return
        status.set_class(False, "-error")

        if self._source is None and self._error:
            status.update(self._error)
            return

        total = len(self._buffer)
        parts = [f"{total:,} lines"]

        if self._query.active:
            matches = sum(1 for line in self._buffer if self._query.matches(line.text))
            mode = "filtered" if self._filter_mode else "highlighted"
            parts.append(f"{matches:,} matching ({mode})")
            if not self._filter_mode and self._match_index >= 0:
                parts.append(f"match {self._match_index + 1}/{len(self._match_offsets)}")

        if self._source is not None:
            if not self._source.followable:
                parts.append("compressed archive, not followable")
            else:
                parts.append("following" if self._follow else "paused")

        status.update("  ·  ".join(parts))
