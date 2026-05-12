import AppKit

/// Floating panel triggered by the quick-start global hotkey. Lets the user enter
/// task / project / mode / duration and shells out to `pomo start ...`.
///
/// Repo/branch are not exposed in the UI — `pomo start` auto-detects via the
/// daemon process's cwd, and `pomo start --last` (from a real shell) can restore
/// the previous session's git context when desired.
final class QuickStartWindowController: NSObject, NSWindowDelegate {
    private var window: NSPanel?
    private var taskField: NSTextField?
    private var projectField: NSTextField?
    private var durationField: NSTextField?
    private var modeControl: NSSegmentedControl?
    private var startButton: NSButton?
    private var cancelButton: NSButton?
    private var statusLabel: NSTextField?

    private let pomoBinary: String

    override init() {
        self.pomoBinary = Self.resolvePomoBinary()
        super.init()
    }

    /// Show the popup, prefill from last session, focus task field.
    func show() {
        if window == nil {
            buildWindow()
        }
        guard let window else { return }

        NSApp.activate(ignoringOtherApps: true)
        window.center()
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(taskField)
        prefillFromLastSession()
        updateDurationEnabled()
        setStatus("")
    }

    // MARK: - Window construction

    private func buildWindow() {
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 360, height: 220),
            styleMask: [.titled, .closable, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.title = "Quick start"
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.delegate = self

        let content = NSView(frame: panel.contentLayoutRect)
        content.translatesAutoresizingMaskIntoConstraints = false

        let taskLabel = makeLabel("Task")
        let task = makeTextField(placeholder: "What are you working on?")
        let projectLabel = makeLabel("Project")
        let project = makeTextField(placeholder: "Optional project")

        let mode = NSSegmentedControl(labels: ["Pomodoro", "Stopwatch"], trackingMode: .selectOne, target: self, action: #selector(modeChanged))
        mode.selectedSegment = 0
        mode.translatesAutoresizingMaskIntoConstraints = false

        let durationLabel = makeLabel("Duration (min)")
        let duration = makeTextField(placeholder: "25")
        duration.stringValue = "25"
        duration.alignment = .right

        let start = NSButton(title: "Start", target: self, action: #selector(startSession))
        start.keyEquivalent = "\r" // Enter
        start.bezelStyle = .rounded

        let cancel = NSButton(title: "Cancel", target: self, action: #selector(cancelClicked))
        cancel.keyEquivalent = "\u{1b}" // Escape
        cancel.bezelStyle = .rounded

        let status = NSTextField(labelWithString: "")
        status.font = NSFont.systemFont(ofSize: 11)
        status.textColor = .secondaryLabelColor
        status.translatesAutoresizingMaskIntoConstraints = false
        status.lineBreakMode = .byTruncatingTail

        let stack = NSStackView(views: [
            row(taskLabel, task),
            row(projectLabel, project),
            row(makeLabel("Mode"), mode),
            row(durationLabel, duration),
            status,
            buttonRow(cancel, start),
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 8
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.edgeInsets = NSEdgeInsets(top: 14, left: 14, bottom: 14, right: 14)

        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: content.topAnchor),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            task.widthAnchor.constraint(equalToConstant: 220),
            project.widthAnchor.constraint(equalToConstant: 220),
            duration.widthAnchor.constraint(equalToConstant: 80),
        ])
        panel.contentView = content

        self.window = panel
        self.taskField = task
        self.projectField = project
        self.modeControl = mode
        self.durationField = duration
        self.startButton = start
        self.cancelButton = cancel
        self.statusLabel = status
    }

    private func row(_ label: NSTextField, _ control: NSView) -> NSView {
        label.translatesAutoresizingMaskIntoConstraints = false
        control.translatesAutoresizingMaskIntoConstraints = false
        let s = NSStackView(views: [label, control])
        s.orientation = .horizontal
        s.alignment = .firstBaseline
        s.spacing = 8
        s.translatesAutoresizingMaskIntoConstraints = false
        label.widthAnchor.constraint(equalToConstant: 100).isActive = true
        label.alignment = .right
        return s
    }

    private func buttonRow(_ cancel: NSButton, _ start: NSButton) -> NSView {
        let s = NSStackView(views: [cancel, start])
        s.orientation = .horizontal
        s.alignment = .centerY
        s.spacing = 8
        s.translatesAutoresizingMaskIntoConstraints = false
        return s
    }

    private func makeLabel(_ text: String) -> NSTextField {
        let f = NSTextField(labelWithString: text)
        f.translatesAutoresizingMaskIntoConstraints = false
        return f
    }

    private func makeTextField(placeholder: String) -> NSTextField {
        let f = NSTextField()
        f.placeholderString = placeholder
        f.translatesAutoresizingMaskIntoConstraints = false
        f.isBezeled = true
        f.bezelStyle = .roundedBezel
        return f
    }

    // MARK: - Actions

    @objc private func modeChanged() {
        updateDurationEnabled()
    }

    private func updateDurationEnabled() {
        let pomodoro = (modeControl?.selectedSegment ?? 0) == 0
        durationField?.isEnabled = pomodoro
        durationField?.textColor = pomodoro ? .labelColor : .disabledControlTextColor
    }

    @objc private func cancelClicked() {
        window?.orderOut(nil)
    }

    @objc private func startSession() {
        let task = (taskField?.stringValue ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !task.isEmpty else {
            setStatus("Task is required.")
            return
        }
        let project = (projectField?.stringValue ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let elapsed = (modeControl?.selectedSegment ?? 0) == 1

        var args: [String] = ["start", task]
        if !project.isEmpty {
            args.append(contentsOf: ["-p", project])
        }
        if elapsed {
            args.append("--elapsed")
        } else {
            let raw = (durationField?.stringValue ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard let mins = Int(raw), mins > 0 else {
                setStatus("Duration must be a positive integer.")
                return
            }
            args.append(contentsOf: ["-d", String(mins)])
        }

        startButton?.isEnabled = false
        cancelButton?.isEnabled = false
        setStatus("Starting…")

        runPomo(args: args) { [weak self] (success, output) in
            DispatchQueue.main.async {
                guard let self else { return }
                self.startButton?.isEnabled = true
                self.cancelButton?.isEnabled = true
                if success {
                    self.window?.orderOut(nil)
                } else {
                    let snippet = output
                        .split(separator: "\n")
                        .first
                        .map(String.init) ?? "Failed to start session."
                    self.setStatus(snippet)
                }
            }
        }
    }

    private func setStatus(_ s: String) {
        statusLabel?.stringValue = s
        statusLabel?.textColor = s.lowercased().contains("starting") ? .secondaryLabelColor : .systemRed
    }

    // MARK: - Subprocess

    private func prefillFromLastSession() {
        runPomo(args: ["last-session", "--json"]) { [weak self] (success, output) in
            guard success else { return }
            let trimmed = output.trimmingCharacters(in: .whitespacesAndNewlines)
            guard
                let data = trimmed.data(using: .utf8),
                let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            else { return }
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                if let task = obj["task"] as? String, (self.taskField?.stringValue ?? "").isEmpty {
                    self.taskField?.stringValue = task
                    self.taskField?.selectText(nil)
                }
                if let project = obj["project"] as? String, (self.projectField?.stringValue ?? "").isEmpty {
                    self.projectField?.stringValue = project
                }
            }
        }
    }

    private func runPomo(args: [String], completion: @escaping (Bool, String) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async { [pomoBinary] in
            let task = Process()
            task.executableURL = URL(fileURLWithPath: pomoBinary)
            task.arguments = args
            let out = Pipe()
            let err = Pipe()
            task.standardOutput = out
            task.standardError = err
            do {
                try task.run()
                task.waitUntilExit()
            } catch {
                completion(false, "Failed to run \(pomoBinary): \(error.localizedDescription)")
                return
            }
            let stdout = String(data: out.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            let stderr = String(data: err.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            let combined = stdout.isEmpty ? stderr : stdout
            completion(task.terminationStatus == 0, combined)
        }
    }

    private static func resolvePomoBinary() -> String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let candidates = [
            "\(home)/.local/bin/pomo",
            "/opt/homebrew/bin/pomo",
            "/usr/local/bin/pomo",
        ]
        for c in candidates {
            if FileManager.default.isExecutableFile(atPath: c) {
                return c
            }
        }
        // Last-resort: ask the shell (login shell so user PATH is loaded).
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/zsh")
        task.arguments = ["-lc", "command -v pomo"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = Pipe()
        do {
            try task.run()
            task.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let resolved = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !resolved.isEmpty, FileManager.default.isExecutableFile(atPath: resolved) {
                return resolved
            }
        } catch {
            // fall through
        }
        return "\(home)/.local/bin/pomo"
    }
}
