import AppKit

/// Handles global distraction hotkey: optional note `NSAlert`, daemon `distract`, 2s bolt flash,
/// and 2s post-success cooldown (GlobalHotkeyManager still applies its own short debounce).
final class DistractionFeedbackController {
    private let client: DaemonClient
    private weak var statusBar: StatusBarController?
    private let notePrompt: Bool

    /// Earliest time another distraction may be logged successfully (only moved on success).
    private var distractionCooldownUntil: Date = .distantPast

    private static let cooldownSeconds: TimeInterval = 2
    private static let flashSeconds: TimeInterval = 2

    init(client: DaemonClient, statusBar: StatusBarController, notePrompt: Bool) {
        self.client = client
        self.statusBar = statusBar
        self.notePrompt = notePrompt
    }

    func handleDistractionHotkey() {
        let now = Date()
        if now < distractionCooldownUntil {
            NSLog("[PomoCLI Timer] Distraction hotkey ignored (post-success cooldown)")
            return
        }

        if notePrompt {
            promptThenMaybeLog()
        } else {
            performDistract(description: nil)
        }
    }

    private func promptThenMaybeLog() {
        NSApp.activate(ignoringOtherApps: true)

        let alert = NSAlert()
        alert.messageText = "Log distraction"
        alert.informativeText = "Optional note. Cancel leaves the distraction unlogged."
        alert.alertStyle = .informational

        let field = NSTextField(string: "")
        field.placeholderString = "Note (optional)"
        field.frame = NSRect(x: 0, y: 0, width: 320, height: 22)
        alert.accessoryView = field

        alert.addButton(withTitle: "Log")
        alert.addButton(withTitle: "Cancel")
        if alert.buttons.count >= 2 {
            alert.buttons[1].keyEquivalent = "\u{1b}"
        }

        let response = alert.runModal()
        if response == .alertSecondButtonReturn {
            return
        }

        let raw = (alert.accessoryView as? NSTextField)?.stringValue ?? ""
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        performDistract(description: trimmed.isEmpty ? nil : trimmed)
    }

    private func performDistract(description: String?) {
        client.distract(description: description) { [weak self] response in
            DispatchQueue.main.async {
                guard let self else { return }
                if response?.status == "ok" {
                    NSLog("[PomoCLI Timer] Distraction logged successfully")
                    self.distractionCooldownUntil = Date().addingTimeInterval(Self.cooldownSeconds)
                    self.statusBar?.flashDistraction(duration: Self.flashSeconds)
                    NSSound(named: "Basso")?.play()
                } else {
                    NSLog("[PomoCLI Timer] Distraction failed: \(response?.message ?? "no active session")")
                }
            }
        }
    }
}
