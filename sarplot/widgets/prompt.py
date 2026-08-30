"""A modal that prompts for a bounded integer."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class IntPromptScreen(ModalScreen[int | None]):
    """Ask for an integer within an inclusive range.

    Dismisses with the chosen value, or None if cancelled.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(
        self,
        title: str,
        detail: str = "",
        *,
        initial: int = 0,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._detail = detail
        self._initial = initial
        self._minimum = minimum
        self._maximum = maximum

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-dialog"):
            yield Label(self._title, id="prompt-title")
            if self._detail:
                yield Static(self._detail, id="prompt-detail")
            yield Input(value=str(self._initial), id="prompt-input")
            yield Static("", id="prompt-error")
            with Horizontal(id="prompt-buttons"):
                yield Button("Cancel", variant="default", id="prompt-cancel")
                yield Button("Apply", variant="primary", id="prompt-ok")

    def on_mount(self) -> None:
        prompt = self.query_one("#prompt-input", Input)
        prompt.focus()
        # Select-all so typing replaces the current value.
        prompt.action_end()

    def _parse(self) -> int | None:
        """Validate the input, surfacing the reason it was rejected."""
        raw = self.query_one("#prompt-input", Input).value.strip()
        error = self.query_one("#prompt-error", Static)

        try:
            value = int(raw)
        except ValueError:
            error.update(f"'{raw}' is not a whole number.")
            return None

        if self._minimum is not None and value < self._minimum:
            error.update(f"Must be at least {self._minimum}.")
            return None
        if self._maximum is not None and value > self._maximum:
            error.update(f"Must be at most {self._maximum}.")
            return None

        error.update("")
        return value

    @on(Button.Pressed, "#prompt-ok")
    @on(Input.Submitted, "#prompt-input")
    def _on_submit(self) -> None:
        value = self._parse()
        if value is not None:
            self.dismiss(value)

    @on(Button.Pressed, "#prompt-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
