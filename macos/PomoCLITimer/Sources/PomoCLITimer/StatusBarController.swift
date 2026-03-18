import AppKit

final class StatusBarController {
    private let statusItem: NSStatusItem
    private let pauseResumeItem: NSMenuItem
    private let stopItem: NSMenuItem
    private var currentState: String = "stopped"
    private let client: DaemonClient

    init(client: DaemonClient) {
        self.client = client

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "🍅"

        pauseResumeItem = NSMenuItem(title: "Pause", action: nil, keyEquivalent: "")
        stopItem = NSMenuItem(title: "Stop", action: nil, keyEquivalent: "")

        let menu = NSMenu()
        menu.addItem(pauseResumeItem)
        menu.addItem(stopItem)
        menu.addItem(NSMenuItem.separator())
        let versionItem = NSMenuItem(title: "PomoCLI Timer \(appBuild)", action: nil, keyEquivalent: "")
        versionItem.isEnabled = false
        menu.addItem(versionItem)
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))

        statusItem.menu = menu

        pauseResumeItem.target = self
        pauseResumeItem.action = #selector(togglePauseResume)
        stopItem.target = self
        stopItem.action = #selector(stopSession)

        updateMenuState()
    }

    func update(state: String, timeLeft: Int) {
        currentState = state

        switch state {
        case "running":
            let mins = timeLeft / 60
            let secs = timeLeft % 60
            statusItem.button?.title = String(format: "🍅 %02d:%02d", mins, secs)
        case "paused":
            let mins = timeLeft / 60
            let secs = timeLeft % 60
            statusItem.button?.title = String(format: "⏸ %02d:%02d", mins, secs)
        default:
            statusItem.button?.title = "🍅"
        }

        updateMenuState()
    }

    func updateDisconnected() {
        currentState = "stopped"
        statusItem.button?.title = "🍅"
        updateMenuState()
    }

    private func updateMenuState() {
        switch currentState {
        case "running":
            pauseResumeItem.title = "Pause"
            pauseResumeItem.isEnabled = true
            stopItem.isEnabled = true
        case "paused":
            pauseResumeItem.title = "Resume"
            pauseResumeItem.isEnabled = true
            stopItem.isEnabled = true
        default:
            pauseResumeItem.title = "Pause"
            pauseResumeItem.isEnabled = false
            stopItem.isEnabled = false
        }
    }

    @objc private func togglePauseResume() {
        if currentState == "running" {
            client.pause { _ in }
        } else if currentState == "paused" {
            client.resume { _ in }
        }
    }

    @objc private func stopSession() {
        client.stop { _ in }
    }

    /// Briefly flash the status bar to indicate a distraction was logged.
    func flashDistraction() {
        let saved = statusItem.button?.title ?? "🍅"
        statusItem.button?.title = "⚡ distraction"
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            self?.statusItem.button?.title = saved
        }
    }
}
