import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusBar: StatusBarController!
    private let client = DaemonClient()
    private var distractionFeedback: DistractionFeedbackController?
    private var hotkeyManager: GlobalHotkeyManager?
    private var idleMonitor: IdleMonitor?
    private var pollTimer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let config = PomoConfig.load()

        NSLog("[PomoCLI Timer] Starting build %@", appBuild)
        statusBar = StatusBarController(client: client)
        distractionFeedback = DistractionFeedbackController(
            client: client,
            statusBar: statusBar,
            notePrompt: config.distractionNotePrompt
        )

        // Set up global hotkey for distractions (2s flash + cooldown on success; optional note alert)
        hotkeyManager = GlobalHotkeyManager(hotkeyString: config.hotkeyDistraction) { [weak self] in
            self?.distractionFeedback?.handleDistractionHotkey()
        }
        hotkeyManager?.register()

        // Set up idle monitor
        idleMonitor = IdleMonitor(
            timeoutSeconds: config.idleTimeout,
            client: client
        )
        idleMonitor?.start()

        // Poll daemon every second
        pollTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.pollStatus()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        pollTimer?.invalidate()
        hotkeyManager?.unregister()
        idleMonitor?.stop()
    }

    private func pollStatus() {
        guard client.isAvailable() else {
            statusBar.updateDisconnected()
            return
        }

        client.status { [weak self] response in
            guard let self, let response, response.status == "ok", let data = response.data else {
                self?.statusBar.updateDisconnected()
                return
            }
            self.statusBar.update(
                state: data.state,
                timeLeft: data.time_left,
                timerMode: data.timer_mode,
                elapsedSeconds: data.elapsed_seconds
            )
        }
    }
}
