import Foundation

struct PomoConfig {
    var idleTimeout: Int = 300
    var soundEnabled: Bool = true
    var hotkeyDistraction: String = "cmd+shift+d"
    var distractionExtendMinutes: Int = 2
    /// When true, macOS menu bar app shows a note field before logging a distraction hotkey.
    var distractionNotePrompt: Bool = false
    /// Global hotkey that opens the quick-start popup window.
    var hotkeyQuickStart: String = "cmd+shift+p"

    static func load() -> PomoConfig {
        var config = PomoConfig()
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let path = "\(home)/.config/pomocli/config.toml"

        guard let contents = try? String(contentsOfFile: path, encoding: .utf8) else {
            return config
        }

        for line in contents.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, !trimmed.hasPrefix("#"), !trimmed.hasPrefix("[") else { continue }

            let parts = trimmed.split(separator: "=", maxSplits: 1)
            guard parts.count == 2 else { continue }

            let key = parts[0].trimmingCharacters(in: .whitespaces)
            var value = parts[1].trimmingCharacters(in: .whitespaces)

            // Strip surrounding quotes
            if value.hasPrefix("\"") && value.hasSuffix("\"") && value.count >= 2 {
                value = String(value.dropFirst().dropLast())
            }

            switch key {
            case "idle_timeout":
                config.idleTimeout = Int(value) ?? config.idleTimeout
            case "sound_enabled":
                config.soundEnabled = (value == "true" || value == "1")
            case "hotkey_distraction":
                config.hotkeyDistraction = value
            case "distraction_extend_minutes":
                config.distractionExtendMinutes = Int(value) ?? config.distractionExtendMinutes
            case "distraction_note_prompt":
                config.distractionNotePrompt = (value == "true" || value == "1")
            case "hotkey_quick_start":
                config.hotkeyQuickStart = value
            default:
                break
            }
        }

        return config
    }
}
