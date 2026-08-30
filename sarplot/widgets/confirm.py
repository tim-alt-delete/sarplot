"""A modal that gates destructive actions behind an explicit confirmation."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ConfirmScreen(ModalScreen[bool]):
    """Ask the user to confirm before doing something irreversible.

    Dismisses with True when confirmed and False otherwise. Escape and the
    Cancel button both decline, and Cancel holds initial focus so a stray
    Enter cannot confirm by accident.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("y", "confirm", "Confirm", show=False),
        Binding("n", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        title: str,
        detail: str = "",
        *,
        confirm_label: str = "Confirm",
        destructive: bool = True,
    ) -> None:
        super().__init__()
        self._title = title
        self._detail = detail
        self._confirm_label = confirm_label
        self._destructive = destructive

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self._title, id="confirm-title")
            if self._detail:
                yield Static(self._detail, id="confirm-detail")
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", variant="default", id="confirm-cancel")
                yield Button(
                    self._confirm_label,
                    variant="error" if self._destructive else "primary",
                    id="confirm-ok",
                )

    def on_mount(self) -> None:
        # Default focus to the safe choice.
        self.query_one("#confirm-cancel", Button).focus()

    @on(Button.Pressed, "#confirm-ok")
    def _on_ok(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
