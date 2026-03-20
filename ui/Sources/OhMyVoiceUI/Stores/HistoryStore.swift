import Foundation
import Combine
import SQLite3

// MARK: - TranscriptionRecord

public struct TranscriptionRecord: Identifiable, Sendable {
    public let id: Int
    public let text: String
    public let durationSeconds: Double
    public let createdAt: String

    public var durationDisplay: String {
        String(format: "%.1f 秒", durationSeconds)
    }

    public var preview: String {
        let lines = text.components(separatedBy: .newlines)
            .prefix(2).joined(separator: " ")
        if lines.count > 100 {
            return String(lines.prefix(100)) + "..."
        }
        return lines
    }
}

// MARK: - HistoryStore

public final class HistoryStore: ObservableObject {
    @Published public var records: [TranscriptionRecord] = []
    @Published public var hasMore: Bool = false

    private let pageSize = 50
    private var currentOffset = 0

    nonisolated(unsafe) var db: OpaquePointer?

    public init(dbPath: String) {
        let flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX
        if sqlite3_open_v2(dbPath, &db, flags, nil) != SQLITE_OK {
            db = nil
        }
    }

    deinit {
        sqlite3_close(db)
    }

    // MARK: - Public API

    public func loadPage() {
        currentOffset = 0
        records = []
        hasMore = false
        let page = fetchPage(offset: 0)
        records = page
        currentOffset = page.count
        hasMore = page.count == pageSize
    }

    public func loadNextPage() {
        let page = fetchPage(offset: currentOffset)
        records.append(contentsOf: page)
        currentOffset += page.count
        if page.count < pageSize {
            hasMore = false
        }
    }

    public func search(query: String) {
        guard let db else { return }
        let sql = """
            SELECT id, text, duration_seconds, created_at
            FROM transcriptions
            WHERE text LIKE ?
            ORDER BY id DESC
        """
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }

        let pattern = "%\(query)%"
        sqlite3_bind_text(stmt, 1, (pattern as NSString).utf8String, -1, nil)

        var result: [TranscriptionRecord] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            result.append(rowToRecord(stmt: stmt))
        }
        records = result
        hasMore = false
    }

    public func refresh() {
        loadPage()
    }

    // MARK: - Private

    private func fetchPage(offset: Int) -> [TranscriptionRecord] {
        guard let db else { return [] }
        let sql = """
            SELECT id, text, duration_seconds, created_at
            FROM transcriptions
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return [] }
        defer { sqlite3_finalize(stmt) }

        sqlite3_bind_int(stmt, 1, Int32(pageSize))
        sqlite3_bind_int(stmt, 2, Int32(offset))

        var result: [TranscriptionRecord] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            result.append(rowToRecord(stmt: stmt))
        }
        return result
    }

    private func rowToRecord(stmt: OpaquePointer?) -> TranscriptionRecord {
        let id = Int(sqlite3_column_int64(stmt, 0))
        let text = String(cString: sqlite3_column_text(stmt, 1))
        let duration = sqlite3_column_double(stmt, 2)
        let createdAt = String(cString: sqlite3_column_text(stmt, 3))
        return TranscriptionRecord(id: id, text: text, durationSeconds: duration, createdAt: createdAt)
    }
}
