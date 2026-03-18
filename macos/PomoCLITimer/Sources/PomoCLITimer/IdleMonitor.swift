import Foundation
import CoreGraphics

final class IdleMonitor {
    private let timeoutSeconds: Double
    private let client: DaemonClient
    private var timer: DispatchSourceTimer?
    private var alreadyPausedForIdle = false

    init(timeoutSeconds: Int, client: DaemonClient) {
        self.timeoutSeconds = Double(timeoutSeconds)
        self.client = client
    }

    func start() {
        let source = DispatchSource.makeTimerSource(queue: DispatchQueue.global(qos: .utility))
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
            // User is active — reset the flag
            alreadyPausedForIdle = false
            return
        }

        // User is idle past threshold
        guard !alreadyPausedForIdle else { return }

        // Check if a session is running before pausing
        client.status { [weak self] response in
            guard let self,
                  let response,
                  response.status == "ok",
                  response.data?.state == "running" else { return }

            self.alreadyPausedForIdle = true
            self.client.pause { _ in }
        }
    }
}
