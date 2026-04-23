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
    #detail-display {
        content-align: center middle;
        height: 1fr;
        color: $text-muted;
    }
    """
    
    def __init__(self, detail: str = "normal"):
        super().__init__()
        self.client = DaemonClient()
        self.detail = detail
        
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("00:00", id="timer-display"),
            Static("Not running", id="status-display"),
            Static("", id="detail-display")
        )
        yield Footer()
        
    def on_mount(self) -> None:
        self.set_interval(1.0, self.update_status)
        
    def update_status(self) -> None:
        response = self.client.status()
        if response.get("status") == "ok":
            data = response.get("data", {})
            state = data.get("state", "stopped")
            mode = data.get("timer_mode", "countdown")
            if mode == "elapsed":
                elapsed = int(data.get("elapsed_seconds", 0))
                mins, secs = divmod(elapsed, 60)
                timer_str = f"{mins:02d}:{secs:02d}"
                label = f"{state.capitalize()} (elapsed)"
            else:
                time_left = data.get("time_left", 0)
                mins, secs = divmod(time_left, 60)
                timer_str = f"{mins:02d}:{secs:02d}"
                label = state.capitalize()

            self.query_one("#timer-display", Static).update(timer_str)
            self.query_one("#status-display", Static).update(label)

            detail_str = ""
            if state != "stopped" and self.detail in ("normal", "full"):
                task = data.get("task_name")
                proj = data.get("project_name")
                if task:
                    detail_str = f"Task: {task}"
                    if proj:
                        detail_str += f" [{proj}]"
                
                if self.detail == "full":
                    duration = data.get("duration", 0)
                    dmins = duration // 60
                    detail_str += f" | {dmins}m"
                    repo = data.get("git_repo")
                    if repo:
                        branch = data.get("git_branch", "")
                        detail_str += f" | {repo}/{branch}"

            self.query_one("#detail-display", Static).update(detail_str)
        else:
            self.query_one("#timer-display", Static).update("--:--")
            self.query_one("#status-display", Static).update("Daemon disconnected")
            self.query_one("#detail-display", Static).update("")

def run_dashboard(detail: str = "normal"):
    app = DashboardApp(detail=detail)
    app.run()
