

from textual.app import App, ComposeResult
from textual.widgets import TabbedContent, TabPane, Static, Label
from textual.containers import Vertical, Horizontal, Grid

text = """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."""

from textual.containers import Container, Grid, VerticalScroll, ScrollableContainer 
from textual.app import App
from textual.widgets import Header, Footer, TabbedContent, TabPane, Tab, Tabs, Sparkline
from textual.events import Resize
from textual.reactive import reactive


class Test(App):
    CSS_PATH = "test2.tcss"

    text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."

    #width = reactive(0)
    def compose(self) -> ComposeResult:
        yield Header()
        #yield Container(Static("Host Information", id="host-info-text"), id="host-info-container")
        yield Grid(
            Static("CPU: 4"),
            Vertical(
                Label("CPU %"),
                Sparkline(data=[1,2,3,4,5,4,3,2,1]),
                Label("Mem Free %"),
                Sparkline(data=[1,2,3,4,5,4,3,2,1]),
                Label("Disk Usage"),
                Sparkline(data=[1,2,3,4,5,4,3,2,1]),
                Label("I/O"),
                Sparkline(data=[1,2,3,4,5,4,3,2,1]),
                Static("Last 24 hrs")
            )
        )
        yield Footer()

    # def on_resize(self, event: Resize) -> None:
    #     width = event.size[0]
    #     if width <= 80: 
    #         self.l1.remove_class("l1")
    #         self.l2.remove_class("l2")
    #         self.l1.add_class("l1-vertical")
    #         self.l2.add_class("l2-vertical")
    #     else:
    #         self.l1.remove_class("l1-vertical")
    #         self.l2.remove_class("l2-vertical")
    #         self.l1.add_class("l1")
    #         self.l2.add_class("l2")

if __name__ == "__main__":
    app = Test()
    app.run()