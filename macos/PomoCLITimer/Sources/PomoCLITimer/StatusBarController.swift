import AppKit

final class StatusBarController {
    private let statusItem: NSStatusItem
    private let quickStartItem: NSMenuItem
    private let logDistractionItem: NSMenuItem
    private let pauseResumeItem: NSMenuItem
    private let stopItem: NSMenuItem
    private let completeItem: NSMenuItem
    private let sessionSeparator: NSMenuItem
    private var currentState: String = "stopped"
    private var currentTimerMode: String = "countdown"
    private let client: DaemonClient
    var onQuickStart: (() -> Void)?
    var onLogDistraction: (() -> Void)?

    private static let statusIconHeight: CGFloat = 18

    /// PNG from the app bundle, drawn as a **template** so AppKit picks menu bar
    /// foreground color (light/dark menu bar, wallpaper tint, etc.).
    private static func statusBarImage() -> NSImage {
        // Prefer the single-stroke asset; `pomocli-status-icon-dark` is a fallback
        // if the primary PNG is missing from the bundle.
        let candidates = ["pomocli-status-icon", "pomocli-status-icon-dark"]
        for name in candidates {
            if let url = Bundle.main.url(forResource: name, withExtension: "png"),
               let image = NSImage(contentsOf: url) {
                let h = statusIconHeight
                let aspect = image.size.width / max(image.size.height, 1)
                image.size = NSSize(width: h * aspect, height: h)
                image.isTemplate = true
                return image
            }
        }
        return emojiImage("🍅")
    }

    /// SF Symbol rendered for the status bar; template so it tracks menu bar styling.
    private static func templateSymbol(_ systemName: String, pointSize: CGFloat = 13) -> NSImage? {
        guard let base = NSImage(systemSymbolName: systemName, accessibilityDescription: nil) else {
            return nil
        }
        let config = NSImage.SymbolConfiguration(pointSize: pointSize, weight: .medium)
        guard let image = base.withSymbolConfiguration(config) else { return nil }
        image.isTemplate = true
        return image
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

        quickStartItem = NSMenuItem(title: "Quick Start…", action: nil, keyEquivalent: "")
        logDistractionItem = NSMenuItem(title: "Log Distraction", action: nil, keyEquivalent: "")
        pauseResumeItem = NSMenuItem(title: "Pause", action: nil, keyEquivalent: "")
        stopItem = NSMenuItem(title: "Stop", action: nil, keyEquivalent: "")
        completeItem = NSMenuItem(title: "Complete Session", action: nil, keyEquivalent: "")
        sessionSeparator = NSMenuItem.separator()

        let menu = NSMenu()
        menu.autoenablesItems = false
        menu.addItem(quickStartItem)
        menu.addItem(logDistractionItem)
        menu.addItem(pauseResumeItem)
        menu.addItem(stopItem)
        menu.addItem(completeItem)
        menu.addItem(sessionSeparator)
        let versionItem = NSMenuItem(title: "PomoCLI Timer \(appBuild)", action: nil, keyEquivalent: "")
        versionItem.isEnabled = false
        menu.addItem(versionItem)
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))

        statusItem.menu = menu

        quickStartItem.target = self
        quickStartItem.action = #selector(triggerQuickStart)
        logDistractionItem.target = self
        logDistractionItem.action = #selector(triggerLogDistraction)
        pauseResumeItem.target = self
        pauseResumeItem.action = #selector(togglePauseResume)
        stopItem.target = self
        stopItem.action = #selector(stopSession)
        completeItem.target = self
        completeItem.action = #selector(completeSession)

        updateMenuState()
    }

    func update(state: String, timeLeft: Int, timerMode: String? = nil, elapsedSeconds: Int? = nil) {
        currentState = state
        currentTimerMode = timerMode ?? "countdown"
        let isElapsed = currentTimerMode == "elapsed"
        let displaySeconds = isElapsed ? (elapsedSeconds ?? 0) : timeLeft
        let mins = displaySeconds / 60
        let secs = displaySeconds % 60

        switch state {
        case "running":
            statusItem.button?.image = Self.statusBarImage()
            if isElapsed {
                statusItem.button?.title = String(format: " ⏱ %02d:%02d", mins, secs)
            } else {
                statusItem.button?.title = String(format: " %02d:%02d", mins, secs)
            }
        case "paused":
            statusItem.button?.image = Self.templateSymbol("pause.fill") ?? Self.emojiImage("⏸")
            if isElapsed {
                statusItem.button?.title = String(format: " ⏱ %02d:%02d", mins, secs)
            } else {
                statusItem.button?.title = String(format: " %02d:%02d", mins, secs)
            }
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
        let isElapsed = currentTimerMode == "elapsed"
        let active = currentState == "running" || currentState == "paused"

        quickStartItem.isHidden = active
        logDistractionItem.isHidden = !active
        pauseResumeItem.isHidden = !active
        stopItem.isHidden = !active
        completeItem.isHidden = !(active && isElapsed)
        completeItem.isEnabled = active && isElapsed

        switch currentState {
        case "running":
            pauseResumeItem.title = "Pause"
            pauseResumeItem.isEnabled = true
            stopItem.isEnabled = true
            logDistractionItem.isEnabled = true
        case "paused":
            pauseResumeItem.title = "Resume"
            pauseResumeItem.isEnabled = true
            stopItem.isEnabled = true
            logDistractionItem.isEnabled = true
        default:
            pauseResumeItem.title = "Pause"
            pauseResumeItem.isEnabled = false
            stopItem.isEnabled = false
            logDistractionItem.isEnabled = false
        }
    }

    @objc private func triggerQuickStart() {
        onQuickStart?()
    }

    @objc private func triggerLogDistraction() {
        onLogDistraction?()
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

    @objc private func completeSession() {
        client.completeSession { _ in }
    }

    /// Briefly flash the status bar to indicate a distraction was logged.
    func flashDistraction(duration: TimeInterval = 2.0) {
        let savedImage = statusItem.button?.image
        let savedTitle = statusItem.button?.title ?? ""
        statusItem.button?.image = Self.templateSymbol("bolt.fill") ?? Self.emojiImage("⚡")
        statusItem.button?.title = " distraction"
        DispatchQueue.main.asyncAfter(deadline: .now() + duration) { [weak self] in
            self?.statusItem.button?.image = savedImage
            self?.statusItem.button?.title = savedTitle
        }
    }
}
