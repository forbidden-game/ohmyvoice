import Foundation

public enum OhMyVoiceUI {
    public static let protocolVersion = 1
}

// MARK: - Shared types

public struct MicDevice: Codable, Sendable {
    public let name: String
    public init(name: String) { self.name = name }
}

// MARK: - Outgoing (Swift → Python)

public enum OutgoingMessage: Sendable {
    case ready
    case reloadModel(quantization: String)
    case updateMic(deviceName: String)
    case toggleAutostart(enabled: Bool)
    case startHotkeyCapture
    case finishHotkeyCapture(modifiers: [String], key: String)
    case cancelHotkeyCapture
    case clearHistory
    case close

    public func toJSONLine() -> Data {
        let dict: [String: Any]
        switch self {
        case .ready:
            dict = ["type": "ready", "protocol": OhMyVoiceUI.protocolVersion]
        case .reloadModel(let quantization):
            dict = ["type": "reload_model", "quantization": quantization]
        case .updateMic(let deviceName):
            dict = ["type": "update_mic", "device_name": deviceName]
        case .toggleAutostart(let enabled):
            dict = ["type": "toggle_autostart", "enabled": enabled]
        case .startHotkeyCapture:
            dict = ["type": "start_hotkey_capture"]
        case .finishHotkeyCapture(let modifiers, let key):
            dict = ["type": "finish_hotkey_capture", "modifiers": modifiers, "key": key]
        case .cancelHotkeyCapture:
            dict = ["type": "cancel_hotkey_capture"]
        case .clearHistory:
            dict = ["type": "clear_history"]
        case .close:
            dict = ["type": "close"]
        }
        // JSONSerialization never fails on [String: Any] with basic types
        return (try? JSONSerialization.data(withJSONObject: dict)) ?? Data()
    }
}

// MARK: - Incoming (Python → Swift)

public struct StatePayload: Sendable {
    public let modelLoaded: Bool
    public let modelName: String
    public let quantization: String
    public let diskUsage: Int
    public let micDevices: [MicDevice]
    public let version: String
}

public enum IncomingMessage: Sendable {
    case state(StatePayload)
    case modelReloading
    case modelReloaded(success: Bool, error: String?)
    case hotkeyPaused
    case autostartDone
    case historyCleared
    case unknown
}

extension IncomingMessage: Equatable {
    public static func == (lhs: IncomingMessage, rhs: IncomingMessage) -> Bool {
        switch (lhs, rhs) {
        case (.modelReloading, .modelReloading),
             (.hotkeyPaused, .hotkeyPaused),
             (.autostartDone, .autostartDone),
             (.historyCleared, .historyCleared),
             (.unknown, .unknown):
            return true
        case let (.modelReloaded(s1, e1), .modelReloaded(s2, e2)):
            return s1 == s2 && e1 == e2
        default:
            return false
        }
    }
}

extension IncomingMessage {
    public static func parse(from data: Data) -> IncomingMessage? {
        guard
            let obj = try? JSONSerialization.jsonObject(with: data),
            let dict = obj as? [String: Any],
            let type_ = dict["type"] as? String
        else { return nil }

        switch type_ {
        case "state":
            guard
                let modelLoaded = dict["model_loaded"] as? Bool,
                let modelName = dict["model_name"] as? String,
                let quantization = dict["quantization"] as? String,
                let diskUsage = dict["disk_usage"] as? Int,
                let version = dict["version"] as? String
            else { return .unknown }
            let rawDevices = dict["mic_devices"] as? [[String: Any]] ?? []
            let micDevices = rawDevices.compactMap { d -> MicDevice? in
                guard let name = d["name"] as? String else { return nil }
                return MicDevice(name: name)
            }
            let payload = StatePayload(
                modelLoaded: modelLoaded,
                modelName: modelName,
                quantization: quantization,
                diskUsage: diskUsage,
                micDevices: micDevices,
                version: version
            )
            return .state(payload)

        case "model_reloading":
            return .modelReloading

        case "model_reloaded":
            let success = dict["success"] as? Bool ?? false
            let error = dict["error"] as? String
            return .modelReloaded(success: success, error: error)

        case "hotkey_paused":
            return .hotkeyPaused

        case "autostart_done":
            return .autostartDone

        case "history_cleared":
            return .historyCleared

        default:
            return .unknown
        }
    }
}
