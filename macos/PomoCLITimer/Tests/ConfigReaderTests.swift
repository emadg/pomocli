// Standalone Foundation test: no AppKit or running macOS GUI is required.
// swiftc Sources/PomoCLITimer/ConfigReader.swift Tests/ConfigReaderTests.swift -o /tmp/pomo-config-tests
import Foundation

@main
struct ConfigReaderTests {
    static func main() {
        let legacy = PomoConfig.parse("""
        idle_timeout = 120
        sound_enabled = false
        hotkey_distraction = "cmd+shift+x"
        hotkey_quick_start = "cmd+shift+s"
        distraction_note_prompt = true
        """)
        precondition(legacy.idleTimeout == 120)
        precondition(!legacy.soundEnabled)
        precondition(legacy.hotkeyDistraction == "cmd+shift+x")
        precondition(legacy.hotkeyQuickStart == "cmd+shift+s")
        precondition(legacy.distractionNotePrompt)

        let shared = PomoConfig.parse("""
        hotkey_distraction = "cmd+shift+d"
        hotkey_quick_start = "cmd+shift+p"
        idle_timeout = 300
        [linux]
        hotkey_distraction = "CTRL+ALT+d"
        hotkey_quick_start = "CTRL+ALT+p"
        idle_timeout = 5
        [linux.extra]
        sound_enabled = false
        """)
        precondition(shared.hotkeyDistraction == "cmd+shift+d")
        precondition(shared.hotkeyQuickStart == "cmd+shift+p")
        precondition(shared.idleTimeout == 300)
        precondition(shared.soundEnabled)
        print("ConfigReader root/table regression checks passed")
    }
}
