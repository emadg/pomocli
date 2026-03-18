from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Container
from ..daemon.client import DaemonClient

class DashboardApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #timer-display {
        content-align: center middle;
        height: 1fr;
        text-style: bold;
    }
    #status-display {
        content-align: center middle;
        height: 1fr;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.client = DaemonClient()
        
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("00:00", id="timer-display"),
            Static("Not running", id="status-display")
        )
        yield Footer()
        
    def on_mount(self) -> None:
        self.set_interval(1.0, self.update_status)
        
    def update_status(self) -> None:
        response = self.client.status()
        if response.get("status") == "ok":
            data = response.get("data", {})
            state = data.get("state", "stopped")
            time_left = data.get("time_left", 0)
            
            mins, secs = divmod(time_left, 60)
            timer_str = f"{mins:02d}:{secs:02d}"
            
            self.query_one("#timer-display", Static).update(timer_str)
            self.query_one("#status-display", Static).update(state.capitalize())
        else:
            self.query_one("#timer-display", Static).update("--:--")
            self.query_one("#status-display", Static).update("Daemon disconnected")

def run_dashboard():
    app = DashboardApp()
    app.run()
