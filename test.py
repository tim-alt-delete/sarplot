# from __future__ import annotations


# from textual.app import App, ComposeResult
# from textual.widgets import TabbedContent, TabPane, Static
# from textual.containers import Vertical, Horizontal, Grid

# text = """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."""

# from textual.containers import Container, Grid, VerticalScroll, ScrollableContainer 
# from textual.app import App
# from textual.widgets import Header, Footer, TabbedContent, TabPane, Tab, Tabs, Sparkline
# from textual.events import Resize
# from textual.reactive import reactive


# class Test(App):
#     CSS_PATH = "test.tcss"

#     text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."

#     #width = reactive(0)
#     def compose(self) -> ComposeResult:

#         self.l1 = VerticalScroll(id="l1", classes="l1", can_focus=True)
#         self.l2 = VerticalScroll(id="l2", classes="l2", can_focus=True)

#         yield Header()
#         with TabbedContent():
#             with TabPane("one"):
#                 with self.l1:
#                     c1 = VerticalScroll (id="c1", can_focus=True)
#                     c1.border_title = "c1"
#                     with c1:
#                         yield Static(text)
#                         yield Sparkline(data=[1,2,3,4,5,4,3,2,1])
#                     c2 = VerticalScroll (id="c2", can_focus=True)
#                     c2.border_title = "c2"
#                     with c2:
#                         yield Static(text)
#                         yield Sparkline(data=[1,2,3,4,5,4,3,2,1])
#                     c3 = VerticalScroll (id="c3", can_focus=True)
#                     c3.border_title = "c3"
#                     with c3:
#                         yield Static(text)
#                     c4 = VerticalScroll (id="c4", can_focus=True)
#                     c4.border_title = "c4"
#                     with c4:
#                         yield Static(text)
#             with TabPane("two"):
#                 with self.l2:
#                     c1 = VerticalScroll (id="c1", can_focus=True)
#                     c1.border_title = "c1"
#                     with c1:
#                         yield Static(text)
#                         yield Sparkline(data=[1,2,3,4,5,4,3,2,1])
#                     c2 = VerticalScroll (id="c2", can_focus=True)
#                     c2.border_title = "c2"
#                     with c2:
#                         yield Static(text)
#                         yield Sparkline(data=[1,2,3,4,5,4,3,2,1])
#                     c3 = VerticalScroll (id="c3", can_focus=True)
#                     c3.border_title = "c3"
#                     with c3:
#                         yield Static(text)
#                     c4 = VerticalScroll (id="c4", can_focus=True)
#                     c4.border_title = "c4"
#                     with c4:
#                         yield Static(text)
#         yield Footer()

#     def on_resize(self, event: Resize) -> None:
#         width = event.size[0]
#         if width <= 80: 
#             self.l1.remove_class("l1")
#             self.l2.remove_class("l2")
#             self.l1.add_class("l1-vertical")
#             self.l2.add_class("l2-vertical")
#         else:
#             self.l1.remove_class("l1-vertical")
#             self.l2.remove_class("l2-vertical")
#             self.l1.add_class("l1")
#             self.l2.add_class("l2")

# if __name__ == "__main__":
#     app = Test()
#     app.run()

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
    CSS_PATH = "test.tcss"

    text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."

    #width = reactive(0)
    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Container(Static("Host Info", id="host-info-static"), id="host-info-container"),
            Horizontal(
                    Static("Intel(R) Xeon(R) Platinum 8473C\ncpus: 4\n"),
                    Sparkline(data=[x for x in range(100)])
            ),
            Horizontal(
                Static("memory: 4G"),
                Vertical(
                    Label("Memory (GB)"),
                    Sparkline(data=[1,2,3,4,5,4,3,2,1]),
                    id = "memory-vertical"
                )
            ),
            Horizontal(
                Static("/: 20G"),
                Sparkline(data=[1,2,3,4,5,4,3,2,1])
            ),  
            id="host-info-vertical"          
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