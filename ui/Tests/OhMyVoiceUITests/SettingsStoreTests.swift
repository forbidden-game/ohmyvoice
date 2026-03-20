import Testing
import Foundation
@testable import OhMyVoiceUI

@Test func loadsDefaultsWhenFileDoesNotExist() throws {
    let path = NSTemporaryDirectory() + "nonexistent_\(UUID().uuidString)/settings.json"
    let store = SettingsStore(filePath: path)

    #expect(store.language == "auto")
    #expect(store.autostart == false)
    #expect(store.notificationOnComplete == false)
    #expect(store.historyMaxEntries == 1000)
    #expect(store.hotkeyModifiers == ["option"])
    #expect(store.hotkeyKey == "space")
    #expect(store.soundFeedback == true)
    #expect(store.maxRecordingSeconds == 60)
    #expect(store.inputDevice == nil)
    #expect(store.modelName == "Qwen3-ASR-0.6B")
    #expect(store.modelQuantization == "4bit")
    #expect(store.activePromptTemplate == "coding")
    #expect(store.customPrompt == "")
    #expect(store.promptTemplates["coding"] != nil)
    #expect(store.promptTemplates["meeting"] != nil)
    #expect(store.promptTemplates["general"] != nil)
}

@Test func loadsFromExistingFile() throws {
    let dir = NSTemporaryDirectory() + "omv_test_\(UUID().uuidString)"
    try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
    let path = dir + "/settings.json"

    let json = """
    {
        "language": "zh",
        "autostart": true,
        "notification_on_complete": true,
        "history_max_entries": 500,
        "hotkey": {"modifiers": ["command"], "key": "r"},
        "audio": {"input_device": "Built-in Microphone", "sound_feedback": false, "max_recording_seconds": 30},
        "model": {"name": "Qwen3-ASR-0.6B", "quantization": "int8", "path": "~/.cache/ohmyvoice/models/"},
        "prompt": {
            "active_template": "meeting",
            "custom_prompt": "custom text",
            "templates": {
                "coding": "code prompt",
                "meeting": "meeting prompt",
                "general": ""
            }
        }
    }
    """
    try json.write(toFile: path, atomically: true, encoding: .utf8)

    let store = SettingsStore(filePath: path)

    #expect(store.language == "zh")
    #expect(store.autostart == true)
    #expect(store.notificationOnComplete == true)
    #expect(store.historyMaxEntries == 500)
    #expect(store.hotkeyModifiers == ["command"])
    #expect(store.hotkeyKey == "r")
    #expect(store.soundFeedback == false)
    #expect(store.maxRecordingSeconds == 30)
    #expect(store.inputDevice == "Built-in Microphone")
    #expect(store.modelQuantization == "int8")
    #expect(store.activePromptTemplate == "meeting")
    #expect(store.customPrompt == "custom text")
    #expect(store.promptTemplates["coding"] == "code prompt")
}

@Test func savesChangesToFile() throws {
    let dir = NSTemporaryDirectory() + "omv_test_\(UUID().uuidString)"
    let path = dir + "/settings.json"
    let store = SettingsStore(filePath: path)

    store.language = "en"
    store.autostart = true
    store.hotkeyKey = "f1"
    try store.save()

    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    let parsed = try JSONSerialization.jsonObject(with: data) as! [String: Any]

    #expect(parsed["language"] as? String == "en")
    #expect(parsed["autostart"] as? Bool == true)
    let hotkey = parsed["hotkey"] as? [String: Any]
    #expect(hotkey?["key"] as? String == "f1")
    let audio = parsed["audio"] as? [String: Any]
    #expect(audio?["sound_feedback"] as? Bool == true)
}

@Test func hotkeyDisplayFormatsCorrectly() throws {
    let path = NSTemporaryDirectory() + "nonexistent_\(UUID().uuidString)/settings.json"
    let store = SettingsStore(filePath: path)

    store.hotkeyModifiers = ["command", "shift"]
    store.hotkeyKey = "space"
    #expect(store.hotkeyDisplay == "⌘⇧SPACE")

    store.hotkeyModifiers = ["option"]
    store.hotkeyKey = "space"
    #expect(store.hotkeyDisplay == "⌥SPACE")

    store.hotkeyModifiers = ["control", "option"]
    store.hotkeyKey = "r"
    #expect(store.hotkeyDisplay == "⌃⌥R")
}
