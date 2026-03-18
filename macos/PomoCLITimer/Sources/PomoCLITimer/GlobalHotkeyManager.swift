import Carbon
import AppKit

final class GlobalHotkeyManager {
    private var hotKeyRef: EventHotKeyRef?
    private var eventHandler: EventHandlerRef?
    private var globalMonitor: Any?
    private let callback: () -> Void
    private let keyCode: UInt32
    private let modifiers: UInt32
    private let cocoaModifiers: NSEvent.ModifierFlags

    init(hotkeyString: String, callback: @escaping () -> Void) {
        self.callback = callback
        let parsed = Self.parse(hotkeyString)
        self.keyCode = parsed.keyCode
        self.modifiers = parsed.carbonModifiers
        self.cocoaModifiers = parsed.cocoaModifiers
    }

    func register() {
        // Try Carbon API first (works without Accessibility in many cases)
        let carbonSuccess = registerCarbon()

        if !carbonSuccess {
            NSLog("[PomoCLI Timer] Carbon hotkey registration failed, trying NSEvent global monitor (requires Accessibility permission)")
        }

        // Also register NSEvent global monitor as fallback/supplement
        // This requires Accessibility permission but is more reliable on modern macOS
        registerCocoaMonitor()
    }

    func unregister() {
        if let ref = hotKeyRef {
            UnregisterEventHotKey(ref)
            hotKeyRef = nil
        }
        if let handler = eventHandler {
            RemoveEventHandler(handler)
            eventHandler = nil
        }
        if let monitor = globalMonitor {
            NSEvent.removeMonitor(monitor)
            globalMonitor = nil
        }
    }

    // MARK: - Carbon hotkey

    private func registerCarbon() -> Bool {
        let hotKeyID = EventHotKeyID(signature: OSType(0x504F4D4F), id: 1) // "POMO"

        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        let selfPtr = Unmanaged.passUnretained(self).toOpaque()

        let handlerStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, userData -> OSStatus in
                guard let userData else { return OSStatus(eventNotHandledErr) }
                let manager = Unmanaged<GlobalHotkeyManager>.fromOpaque(userData).takeUnretainedValue()
                NSLog("[PomoCLI Timer] Global hotkey pressed (Carbon)")
                manager.callback()
                return noErr
            },
            1,
            &eventType,
            selfPtr,
            &eventHandler
        )

        guard handlerStatus == noErr else {
            NSLog("[PomoCLI Timer] Failed to install Carbon event handler: \(handlerStatus)")
            return false
        }

        var ref: EventHotKeyRef?
        let registerStatus = RegisterEventHotKey(
            keyCode, modifiers, hotKeyID,
            GetApplicationEventTarget(), 0, &ref
        )

        guard registerStatus == noErr else {
            NSLog("[PomoCLI Timer] Failed to register Carbon hotkey: \(registerStatus)")
            return false
        }

        hotKeyRef = ref
        NSLog("[PomoCLI Timer] Carbon hotkey registered (keyCode=\(keyCode), modifiers=\(modifiers))")
        return true
    }

    // MARK: - Cocoa global monitor (fallback)

    private func registerCocoaMonitor() {
        let requiredModifiers: NSEvent.ModifierFlags = cocoaModifiers
        let targetKeyCode = UInt16(keyCode)

        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            let eventMods = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            if event.keyCode == targetKeyCode && eventMods == requiredModifiers {
                NSLog("[PomoCLI Timer] Global hotkey pressed (Cocoa monitor)")
                self?.callback()
            }
        }

        if globalMonitor != nil {
            NSLog("[PomoCLI Timer] Cocoa global monitor registered")
        } else {
            NSLog("[PomoCLI Timer] Cocoa global monitor failed (Accessibility permission may be needed)")
        }
    }

    // MARK: - Hotkey string parsing

    private struct ParsedHotkey {
        let keyCode: UInt32
        let carbonModifiers: UInt32
        let cocoaModifiers: NSEvent.ModifierFlags
    }

    private static func parse(_ hotkeyString: String) -> ParsedHotkey {
        let tokens = hotkeyString.lowercased().split(separator: "+").map {
            $0.trimmingCharacters(in: .whitespaces)
        }
        var carbonMods: UInt32 = 0
        var cocoaMods: NSEvent.ModifierFlags = []
        var keyCode: UInt32 = UInt32(kVK_ANSI_D)

        for token in tokens {
            switch token {
            case "cmd", "command":
                carbonMods |= UInt32(cmdKey)
                cocoaMods.insert(.command)
            case "shift":
                carbonMods |= UInt32(shiftKey)
                cocoaMods.insert(.shift)
            case "ctrl", "control":
                carbonMods |= UInt32(controlKey)
                cocoaMods.insert(.control)
            case "opt", "alt", "option":
                carbonMods |= UInt32(optionKey)
                cocoaMods.insert(.option)
            default:
                if let code = keyCodeMap[token] {
                    keyCode = code
                }
            }
        }

        return ParsedHotkey(keyCode: keyCode, carbonModifiers: carbonMods, cocoaModifiers: cocoaMods)
    }

    private static let keyCodeMap: [String: UInt32] = [
        "a": UInt32(kVK_ANSI_A), "b": UInt32(kVK_ANSI_B), "c": UInt32(kVK_ANSI_C),
        "d": UInt32(kVK_ANSI_D), "e": UInt32(kVK_ANSI_E), "f": UInt32(kVK_ANSI_F),
        "g": UInt32(kVK_ANSI_G), "h": UInt32(kVK_ANSI_H), "i": UInt32(kVK_ANSI_I),
        "j": UInt32(kVK_ANSI_J), "k": UInt32(kVK_ANSI_K), "l": UInt32(kVK_ANSI_L),
        "m": UInt32(kVK_ANSI_M), "n": UInt32(kVK_ANSI_N), "o": UInt32(kVK_ANSI_O),
        "p": UInt32(kVK_ANSI_P), "q": UInt32(kVK_ANSI_Q), "r": UInt32(kVK_ANSI_R),
        "s": UInt32(kVK_ANSI_S), "t": UInt32(kVK_ANSI_T), "u": UInt32(kVK_ANSI_U),
        "v": UInt32(kVK_ANSI_V), "w": UInt32(kVK_ANSI_W), "x": UInt32(kVK_ANSI_X),
        "y": UInt32(kVK_ANSI_Y), "z": UInt32(kVK_ANSI_Z),
        "0": UInt32(kVK_ANSI_0), "1": UInt32(kVK_ANSI_1), "2": UInt32(kVK_ANSI_2),
        "3": UInt32(kVK_ANSI_3), "4": UInt32(kVK_ANSI_4), "5": UInt32(kVK_ANSI_5),
        "6": UInt32(kVK_ANSI_6), "7": UInt32(kVK_ANSI_7), "8": UInt32(kVK_ANSI_8),
        "9": UInt32(kVK_ANSI_9),
        "space": UInt32(kVK_Space), "return": UInt32(kVK_Return), "tab": UInt32(kVK_Tab),
        "escape": UInt32(kVK_Escape), "delete": UInt32(kVK_Delete),
        "f1": UInt32(kVK_F1), "f2": UInt32(kVK_F2), "f3": UInt32(kVK_F3),
        "f4": UInt32(kVK_F4), "f5": UInt32(kVK_F5), "f6": UInt32(kVK_F6),
        "f7": UInt32(kVK_F7), "f8": UInt32(kVK_F8), "f9": UInt32(kVK_F9),
        "f10": UInt32(kVK_F10), "f11": UInt32(kVK_F11), "f12": UInt32(kVK_F12),
    ]
}
