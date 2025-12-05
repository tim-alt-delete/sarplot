from textual.app import App, ComposeResult
from textual.widgets import TabbedContent, TabPane, Static
from textual.containers import Vertical, Horizontal, Grid

text = """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."""

class ExampleApp(App):

    CSS_PATH = "test.tcss"
    def compose(self) -> ComposeResult:
        with TabbedContent():

            with TabPane('a'):
                yield Static('1', classes="box")
                yield Static('2', classes="box")
                yield Static('3', classes="box")

            with TabPane('b'):
                with Vertical():
                    yield Static('1', classes="box")
                    yield Static('2', classes="box")
                    yield Static('3', classes="box")

            with TabPane('c'):
                with Horizontal():
                    yield Static('1', classes="box")
                    yield Static('2', classes="box")
                    yield Static('3', classes="box")

            with TabPane('d'):
                with Vertical():
                    with Horizontal():
                        yield Static('1', classes="box")
                        yield Static('2', classes="box")
                    with Horizontal():
                        yield Static('3', classes="box")
                        yield Static('4', classes="box")

            with TabPane('e'):
                with Grid(id="grid"):
                    yield Static(text, classes="grid-box")
                    yield Static(text, classes="grid-box")
                    yield Static(text, classes="grid-box")
                    yield Static(text, classes="grid-box")
                    yield Static(text, classes="grid-box")
                    yield Static(text, classes="grid-box")
if __name__ == '__main__':
    app = ExampleApp()
    app.run()

# from textual.app import App, ComposeResult
# from textual.containers import Container, Horizontal, VerticalScroll
# from textual.widgets import Header, Static


# class CombiningLayoutsExample(App):
#     CSS_PATH = "test.tcss"

#     def compose(self) -> ComposeResult:
#         yield Header()
#         with Container(id="app-grid"):
#             with VerticalScroll(id="left-pane"):
#                 for number in range(15):
#                     yield Static(f"Vertical layout, child {number}")
#             with Horizontal(id="top-right"):
#                 yield Static("Horizontally")
#                 yield Static("Positioned")
#                 yield Static("Children")
#                 yield Static("Here")
#             with Container(id="bottom-right"):
#                 yield Static("This")
#                 yield Static("panel")
#                 yield Static("is")
#                 yield Static("using")
#                 yield Static("grid layout!", id="bottom-right-final")


# if __name__ == "__main__":
#     app = CombiningLayoutsExample()
#     app.run()