import AppKit

final class StatusBarController {
    private let statusItem: NSStatusItem
    private let pauseResumeItem: NSMenuItem
    private let stopItem: NSMenuItem
    private var currentState: String = "stopped"
    private let client: DaemonClient

    private static let statusIconHeight: CGFloat = 18

    /// PNG from the app bundle; use a dark variant when macOS is in dark mode.
    private static func statusBarImage() -> NSImage {
        let isDark = NSApp.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let candidates = isDark
            ? ["pomocli-status-icon-dark", "pomocli-status-icon"]
            : ["pomocli-status-icon"]
        for name in candidates {
            if let url = Bundle.main.url(forResource: name, withExtension: "png"),
               let image = NSImage(contentsOf: url) {
                let h = statusIconHeight
                let aspect = image.size.width / max(image.size.height, 1)
                image.size = NSSize(width: h * aspect, height: h)
                image.isTemplate = false
                return image
            }
        }
        return emojiImage("🍅")
    }

    private static func emojiImage(_ emoji: String, size: CGFloat = 18) -> NSImage {
        let font = NSFont.systemFont(ofSize: size)
        let attrs: [NSAttributedString.Key: Any] = [.font: font]
        let textSize = (emoji as NSString).size(withAttributes: attrs)
        let imgSize = NSSize(width: ceil(textSize.width), height: ceil(textSize.height))
        let image = NSImage(size: imgSize)
        image.lockFocus()
        (emoji as NSString).draw(at: .zero, withAttributes: attrs)
        image.unlockFocus()
        image.isTemplate = false
        return image
    }

    init(client: DaemonClient) {
        self.client = client

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.image = Self.statusBarImage()
        statusItem.button?.imagePosition = .imageLeading
        statusItem.button?.title = ""

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
        let mins = timeLeft / 60
        let secs = timeLeft % 60

        switch state {
        case "running":
            statusItem.button?.image = Self.statusBarImage()
            statusItem.button?.title = String(format: " %02d:%02d", mins, secs)
        case "paused":
            statusItem.button?.image = Self.emojiImage("⏸")
            statusItem.button?.title = String(format: " %02d:%02d", mins, secs)
        default:
            statusItem.button?.image = Self.statusBarImage()
            statusItem.button?.title = ""
        }

        updateMenuState()
    }

    func updateDisconnected() {
        currentState = "stopped"
        statusItem.button?.image = Self.statusBarImage()
        statusItem.button?.title = ""
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
        let savedImage = statusItem.button?.image
        let savedTitle = statusItem.button?.title ?? ""
        statusItem.button?.image = Self.emojiImage("⚡")
        statusItem.button?.title = " distraction"
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            self?.statusItem.button?.image = savedImage
            self?.statusItem.button?.title = savedTitle
        }
    }
}
