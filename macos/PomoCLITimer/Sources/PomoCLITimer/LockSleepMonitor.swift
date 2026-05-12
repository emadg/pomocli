import AppKit
import Foundation

final class LockSleepMonitor {
    private let client: DaemonClient
    private var didAutoPauseForLock = false
    private var isShowingLockReturnPrompt = false
    private var observerTokens: [NSObjectProtocol] = []

    init(client: DaemonClient) {
        self.client = client
    }

    func start() {
        let nc = NSWorkspace.shared.notificationCenter
        let sleepEvents: [NSNotification.Name] = [
            NSWorkspace.screensDidSleepNotification,
            NSWorkspace.willSleepNotification,
            NSWorkspace.sessionDidResignActiveNotification,
        ]
        let wakeEvents: [NSNotification.Name] = [
            NSWorkspace.screensDidWakeNotification,
            NSWorkspace.didWakeNotification,
            NSWorkspace.sessionDidBecomeActiveNotification,
        ]
        for name in sleepEvents {
            let token = nc.addObserver(forName: name, object: nil, queue: nil) { [weak self] _ in
                DispatchQueue.main.async { self?.onLockOrSleep() }
            }
            observerTokens.append(token)
        }
        for name in wakeEvents {
            let token = nc.addObserver(forName: name, object: nil, queue: nil) { [weak self] _ in
                DispatchQueue.main.async { self?.onUnlockOrWake() }
            }
            observerTokens.append(token)
        }
    }

    func stop() {
        let nc = NSWorkspace.shared.notificationCenter
        for token in observerTokens {
            nc.removeObserver(token)
        }
        observerTokens.removeAll()
    }

    private func onLockOrSleep() {
        client.status { [weak self] response in
            guard let self,
                  let response,
                  response.status == "ok",
                  response.data?.state == "running" else { return }
            self.didAutoPauseForLock = true
            self.client.pause(source: "screen_lock") { _ in }
        }
    }

    private func onUnlockOrWake() {
        guard didAutoPauseForLock else { return }
        didAutoPauseForLock = false
        presentLockReturnPromptIfNeeded()
    }

    private func presentLockReturnPromptIfNeeded() {
        guard !isShowingLockReturnPrompt else { return }
        isShowingLockReturnPrompt = true

        client.status { [weak self] response in
            defer { self?.isShowingLockReturnPrompt = false }
            guard let self,
                  let response,
                  response.status == "ok",
                  response.data?.state == "paused" else { return }

            NSApp.activate(ignoringOtherApps: true)

            let alert = NSAlert()
            alert.messageText = "Session paused"
            alert.informativeText = "Your Pomodoro session was paused because your Mac was locked or asleep."
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
