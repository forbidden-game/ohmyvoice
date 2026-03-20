import AppKit
import SwiftUI
import OhMyVoiceUI

// --- Argument parsing ---
let args = CommandLine.arguments
guard args.count >= 2 else {
    fputs("Usage: ohmyvoice-ui <preferences|history> [--settings PATH | --db PATH]\n", stderr)
    exit(1)
}

let command = args[1]

func argValue(for flag: String) -> String? {
    if let idx = args.firstIndex(of: flag), idx + 1 < args.count {
        return args[idx + 1]
    }
    return nil
}

// --- App setup ---
let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let transport = StdioTransport()

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?
    var bridge: IPCBridge?

    func applicationDidFinishLaunching(_ notification: Notification) {
        switch command {
        case "preferences":
            let settingsPath = argValue(for: "--settings")
                ?? NSHomeDirectory() + "/.config/ohmyvoice/settings.json"
            showPreferences(settingsPath: settingsPath)
        case "history":
            let dbPath = argValue(for: "--db")
                ?? NSHomeDirectory() + "/.local/share/ohmyvoice/history.db"
            showHistory(dbPath: dbPath)
        default:
            fputs("Unknown command: \(command)\n", stderr)
            exit(1)
        }
    }

    func showPreferences(settingsPath: String) {
        let bridge = IPCBridge(transport: transport)
        self.bridge = bridge
        let settings = SettingsStore(filePath: settingsPath)
        let view = PreferencesView(settings: settings, bridge: bridge)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 460),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "OhMyVoice 设置"
        window.contentView = NSHostingView(rootView: view)
        window.center()
        window.delegate = self
        window.makeKeyAndOrderFront(nil)
        self.window = window

        bridge.startListening()
        app.activate(ignoringOtherApps: true)
    }

    func showHistory(dbPath: String) {
        let bridge = IPCBridge(transport: transport)
        self.bridge = bridge
        let store = HistoryStore(dbPath: dbPath)
        let view = HistoryView(store: store, bridge: bridge)

        // Listen for history_cleared to refresh
        let observation = bridge.$lastMessage.sink { message in
            if case .historyCleared = message {
                store.refresh()
            }
        }
        // Keep observation alive by associating it with self
        objc_setAssociatedObject(self, "historySink", observation, .OBJC_ASSOCIATION_RETAIN)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 500),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "转写历史"
        window.contentView = NSHostingView(rootView: view)
        window.center()
        window.delegate = self
        window.makeKeyAndOrderFront(nil)
        self.window = window

        bridge.startListening()
        app.activate(ignoringOtherApps: true)
    }
}

extension AppDelegate: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        transport.send(OutgoingMessage.close.toJSONLine())
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            exit(0)
        }
    }
}

let delegate = AppDelegate()
app.delegate = delegate
app.run()
