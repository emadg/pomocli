import Foundation

struct StatusData: Codable {
    let state: String
    let time_left: Int
    let duration: Int
    let session_id: Int?
    /// `"countdown"` (default) or `"elapsed"` stopwatch sessions.
    let timer_mode: String?
    let elapsed_seconds: Int?
}

struct DaemonResponse {
    let status: String
    let message: String?
    let data: StatusData?
}

final class DaemonClient {
    private let socketPath: String
    private let queue = DispatchQueue(label: "com.pomocli.daemon-client", qos: .userInitiated)

    init() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        socketPath = "\(home)/.config/pomocli/pomo.sock"
    }

    // MARK: - Public API

    func status(completion: @escaping (DaemonResponse?) -> Void) {
        sendCommand("status", completion: completion)
    }

    func pause(completion: @escaping (DaemonResponse?) -> Void) {
        sendCommand("pause", completion: completion)
    }

    func resume(completion: @escaping (DaemonResponse?) -> Void) {
        sendCommand("resume", completion: completion)
    }

    func stop(completion: @escaping (DaemonResponse?) -> Void) {
        sendCommand("stop", completion: completion)
    }

    func distract(description: String? = nil, completion: @escaping (DaemonResponse?) -> Void) {
        var args: [String: Any] = [:]
        if let desc = description {
            args["description"] = desc
        }
        sendCommand("distract", args: args, completion: completion)
    }

    func ping(completion: @escaping (DaemonResponse?) -> Void) {
        sendCommand("ping", completion: completion)
    }

    func isAvailable() -> Bool {
        FileManager.default.fileExists(atPath: socketPath)
    }

    // MARK: - Socket I/O

    private func sendCommand(_ command: String, args: [String: Any] = [:], completion: @escaping (DaemonResponse?) -> Void) {
        queue.async { [socketPath] in
            let result = Self.sendSync(socketPath: socketPath, command: command, args: args)
            DispatchQueue.main.async {
                completion(result)
            }
        }
    }

    private static func sendSync(socketPath: String, command: String, args: [String: Any]) -> DaemonResponse? {
        let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        defer { Darwin.close(fd) }

        // Set 2-second send/recv timeout
        var tv = timeval(tv_sec: 2, tv_usec: 0)
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))

        // Connect to Unix domain socket
        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let pathBytes = socketPath.utf8CString
        guard pathBytes.count <= MemoryLayout.size(ofValue: addr.sun_path) else { return nil }
        withUnsafeMutablePointer(to: &addr.sun_path) { sunPathPtr in
            sunPathPtr.withMemoryRebound(to: CChar.self, capacity: pathBytes.count) { dest in
                for i in 0..<pathBytes.count {
                    dest[i] = pathBytes[i]
                }
            }
        }

        let connectResult = withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPtr in
                Darwin.connect(fd, sockaddrPtr, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        guard connectResult == 0 else { return nil }

        // Build JSON request
        var request: [String: Any] = ["command": command]
        if !args.isEmpty {
            request["args"] = args
        }
        guard let jsonData = try? JSONSerialization.data(withJSONObject: request),
              let jsonString = String(data: jsonData, encoding: .utf8) else { return nil }

        // Send
        let sendBytes = jsonString.utf8CString
        let sent = sendBytes.withUnsafeBufferPointer { buf in
            Darwin.send(fd, buf.baseAddress!, buf.count - 1, 0) // exclude null terminator
        }
        guard sent > 0 else { return nil }

        // Receive
        var buffer = [CChar](repeating: 0, count: 4096)
        let received = Darwin.recv(fd, &buffer, buffer.count - 1, 0)
        guard received > 0 else { return nil }
        buffer[received] = 0

        let responseString = String(cString: buffer)
        guard let responseData = responseString.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: responseData) as? [String: Any] else {
            return nil
        }

        // Parse response
        let status = json["status"] as? String ?? "error"
        let message = json["message"] as? String

        var statusData: StatusData?
        if let dataDict = json["data"] as? [String: Any] {
            statusData = StatusData(
                state: dataDict["state"] as? String ?? "stopped",
                time_left: dataDict["time_left"] as? Int ?? 0,
                duration: dataDict["duration"] as? Int ?? 0,
                session_id: dataDict["session_id"] as? Int,
                timer_mode: dataDict["timer_mode"] as? String,
                elapsed_seconds: dataDict["elapsed_seconds"] as? Int
            )
        }

        return DaemonResponse(status: status, message: message, data: statusData)
    }
}
