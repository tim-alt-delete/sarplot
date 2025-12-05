Logs: Usually in /var/log/sa/saDD (DD = day of month).


```python
from textual.app import App, ComposeResult
from textual.widgets import TabbedContent, TabPane, Label
from textual.containers import Vertical, Horizontal

class ExampleApp(App):

    def compose(self) -> ComposeResult:
        with TabbedContent():

            with TabPane('a'):
                yield Label('1')
                yield Label('2')
                yield Label('3')

            with TabPane('b'):
                with Vertical():
                    yield Label('1')
                    yield Label('2')
                    yield Label('3')

            with TabPane('c'):
                with Vertical():
                    with Horizontal():
                        yield Label('1')
                    with Horizontal():
                        yield Label('2')
                    with Horizontal():
                        yield Label('3')

            with TabPane('d'):
                yield Label('1')
                with Vertical():
                    yield Label('2')
                    yield Label('3')
                yield Label('4')

if __name__ == '__main__':
    app = ExampleApp()
    app.run()
```