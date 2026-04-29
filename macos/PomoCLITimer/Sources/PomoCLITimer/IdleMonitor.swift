import AppKit
import CoreGraphics
import Foundation

final class IdleMonitor {
    private let timeoutSeconds: Double
    private let client: DaemonClient
    private var timer: DispatchSourceTimer?
    /// True after we issued pause due to idle for this idle stint; cleared when the user is active again and we have handled return (prompt or skip).
    private var didAutoPauseThisIdleStretch = false
    private var isShowingIdleReturnPrompt = false

    init(timeoutSeconds: Int, client: DaemonClient) {
        self.timeoutSeconds = Double(timeoutSeconds)
        self.client = client
    }

    func start() {
        // Main queue keeps idle flags and NSAlert serialization consistent with DaemonClient completions.
        let source = DispatchSource.makeTimerSource(queue: .main)
        source.schedule(deadline: .now() + 10, repeating: 10)
        source.setEventHandler { [weak self] in
            self?.checkIdle()
        }
        source.resume()
        timer = source
    }

    func stop() {
        timer?.cancel()
        timer = nil
    }

    private func checkIdle() {
        let idleTime = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .mouseMoved)
        let idleKeyboard = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .keyDown)
        let minIdle = min(idleTime, idleKeyboard)

        if minIdle < timeoutSeconds {
            if didAutoPauseThisIdleStretch {
                didAutoPauseThisIdleStretch = false
                presentIdleReturnPromptIfNeeded()
            }
            return
        }

        // User is idle past threshold
        guard !didAutoPauseThisIdleStretch else { return }

        client.status { [weak self] response in
            guard let self,
                  let response,
                  response.status == "ok",
                  response.data?.state == "running" else { return }

            self.didAutoPauseThisIdleStretch = true
            self.client.pause { _ in }
        }
    }

    private func presentIdleReturnPromptIfNeeded() {
        guard !isShowingIdleReturnPrompt else { return }
        isShowingIdleReturnPrompt = true

        client.status { [weak self] response in
            defer { self?.isShowingIdleReturnPrompt = false }
            guard let self,
                  let response,
                  response.status == "ok",
                  response.data?.state == "paused" else { return }

            NSApp.activate(ignoringOtherApps: true)

            let alert = NSAlert()
            alert.messageText = "Session paused"
            alert.informativeText = "Your Pomodoro session was paused because your Mac was idle."
            alert.addButton(withTitle: "Resume")
            alert.addButton(withTitle: "Stop")
            if alert.buttons.count > 1 {
                alert.buttons[1].hasDestructiveAction = true
            }

            switch alert.runModal() {
            case .alertFirstButtonReturn:
                self.client.resume { _ in }
            case .alertSecondButtonReturn:
                self.client.stop { _ in }
            default:
                break
            }
        }
    }
}
