import Foundation
import Combine

// MARK: - Defaults

private enum Defaults {
    static let language = "auto"
    static let autostart = false
    static let notificationOnComplete = false
    static let historyMaxEntries = 1000
    static let hotkeyModifiers = ["option"]
    static let hotkeyKey = "space"
    static let inputDevice: String? = nil
    static let soundFeedback = true
    static let maxRecordingSeconds = 60
    static let modelName = "Qwen3-ASR-0.6B"
    static let modelQuantization = "4bit"
    static let modelPath = "~/.cache/ohmyvoice/models/"
    static let activePromptTemplate = "coding"
    static let customPrompt = ""
    static let promptTemplates: [String: String] = [
        "coding": "这是一位程序员对 coding agent 的口述指令。",
        "meeting": "这是一段会议讨论录音，可能涉及多人发言。",
        "general": "",
    ]
}

// MARK: - SettingsStore

public final class SettingsStore: ObservableObject {
    // MARK: Published (flat)

    @Published public var language: String
    @Published public var autostart: Bool
    @Published public var notificationOnComplete: Bool
    @Published public var historyMaxEntries: Int

    @Published public var hotkeyModifiers: [String]
    @Published public var hotkeyKey: String

    @Published public var inputDevice: String?
    @Published public var soundFeedback: Bool
    @Published public var maxRecordingSeconds: Int

    @Published public var modelQuantization: String

    @Published public var activePromptTemplate: String
    @Published public var customPrompt: String

    // MARK: Read-only

    public private(set) var modelName: String
    public private(set) var promptTemplates: [String: String]

    // MARK: Private

    private let filePath: String

    // MARK: Init

    public init(filePath: String) {
        self.filePath = filePath

        // Start with defaults; overlay with whatever is in the file.
        var raw: [String: Any] = [:]
        if let data = try? Data(contentsOf: URL(fileURLWithPath: filePath)),
           let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        {
            raw = parsed
        }

        let hotkey = raw["hotkey"] as? [String: Any] ?? [:]
        let audio = raw["audio"] as? [String: Any] ?? [:]
        let model = raw["model"] as? [String: Any] ?? [:]
        let prompt = raw["prompt"] as? [String: Any] ?? [:]
        let templates = prompt["templates"] as? [String: String] ?? [:]

        language = raw["language"] as? String ?? Defaults.language
        autostart = raw["autostart"] as? Bool ?? Defaults.autostart
        notificationOnComplete = raw["notification_on_complete"] as? Bool ?? Defaults.notificationOnComplete
        historyMaxEntries = raw["history_max_entries"] as? Int ?? Defaults.historyMaxEntries

        hotkeyModifiers = hotkey["modifiers"] as? [String] ?? Defaults.hotkeyModifiers
        hotkeyKey = hotkey["key"] as? String ?? Defaults.hotkeyKey

        // input_device can be null in JSON → treat as nil
        if let deviceValue = audio["input_device"] {
            inputDevice = deviceValue is NSNull ? nil : deviceValue as? String
        } else {
            inputDevice = Defaults.inputDevice
        }
        soundFeedback = audio["sound_feedback"] as? Bool ?? Defaults.soundFeedback
        maxRecordingSeconds = audio["max_recording_seconds"] as? Int ?? Defaults.maxRecordingSeconds

        modelName = model["name"] as? String ?? Defaults.modelName
        modelQuantization = model["quantization"] as? String ?? Defaults.modelQuantization

        activePromptTemplate = prompt["active_template"] as? String ?? Defaults.activePromptTemplate
        customPrompt = prompt["custom_prompt"] as? String ?? Defaults.customPrompt

        // Deep-merge templates: keep any keys from the file, fill missing with defaults.
        var mergedTemplates = Defaults.promptTemplates
        for (k, v) in templates { mergedTemplates[k] = v }
        promptTemplates = mergedTemplates
    }

    // MARK: Computed

    private static let modifierSymbolMap: [String: String] = [
        "control": "⌃",
        "option": "⌥",
        "shift": "⇧",
        "command": "⌘",
    ]

    /// Human-readable hotkey string, e.g. "⌥SPACE" or "⌘⇧R".
    /// Modifier symbols appear in the same order as `hotkeyModifiers`.
    public var hotkeyDisplay: String {
        let modPart = hotkeyModifiers
            .compactMap { Self.modifierSymbolMap[$0] }
            .joined()
        return modPart + hotkeyKey.uppercased()
    }

    /// Text of the currently active prompt template (custom_prompt takes precedence when non-empty).
    public func activePromptText() -> String {
        if !customPrompt.isEmpty { return customPrompt }
        return promptTemplates[activePromptTemplate] ?? ""
    }

    // MARK: Persistence

    public func save() throws {
        let dict: [String: Any] = [
            "language": language,
            "autostart": autostart,
            "notification_on_complete": notificationOnComplete,
            "history_max_entries": historyMaxEntries,
            "hotkey": [
                "modifiers": hotkeyModifiers,
                "key": hotkeyKey,
            ],
            "audio": [
                "input_device": inputDevice as Any? ?? NSNull(),
                "sound_feedback": soundFeedback,
                "max_recording_seconds": maxRecordingSeconds,
            ],
            "model": [
                "name": modelName,
                "quantization": modelQuantization,
                "path": Defaults.modelPath,
            ],
            "prompt": [
                "active_template": activePromptTemplate,
                "custom_prompt": customPrompt,
                "templates": promptTemplates,
            ],
        ]

        let data = try JSONSerialization.data(withJSONObject: dict, options: [.prettyPrinted, .sortedKeys])

        let dir = URL(fileURLWithPath: filePath).deletingLastPathComponent().path
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)

        try data.write(to: URL(fileURLWithPath: filePath), options: .atomic)
    }
}
