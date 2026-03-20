import Testing
import Foundation
import SQLite3
@testable import OhMyVoiceUI

func makeTempDB(records: [(String, Double, String)]) throws -> String {
    let path = FileManager.default.temporaryDirectory
        .appendingPathComponent(UUID().uuidString + ".db").path
    var db: OpaquePointer?
    sqlite3_open(path, &db)
    sqlite3_exec(db, """
        CREATE TABLE transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            duration_seconds REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """, nil, nil, nil)
    for (text, duration, date) in records {
        let sql = "INSERT INTO transcriptions (text, duration_seconds, created_at) VALUES (?, ?, ?)"
        var stmt: OpaquePointer?
        sqlite3_prepare_v2(db, sql, -1, &stmt, nil)
        sqlite3_bind_text(stmt, 1, (text as NSString).utf8String, -1, nil)
        sqlite3_bind_double(stmt, 2, duration)
        sqlite3_bind_text(stmt, 3, (date as NSString).utf8String, -1, nil)
        sqlite3_step(stmt)
        sqlite3_finalize(stmt)
    }
    sqlite3_close(db)
    return path
}

@Test func loadsRecentRecords() throws {
    let path = try makeTempDB(records: [
        ("Hello world", 1.5, "2024-01-01 10:00:00"),
        ("Goodbye world", 2.0, "2024-01-02 10:00:00"),
    ])
    let store = HistoryStore(dbPath: path)
    store.loadPage()

    #expect(store.records.count == 2)
    // ORDER BY id DESC — second inserted row comes first
    #expect(store.records[0].text == "Goodbye world")
    #expect(store.records[1].text == "Hello world")
}

@Test func searchFiltersResults() throws {
    let path = try makeTempDB(records: [
        ("Hello world", 1.0, "2024-01-01 10:00:00"),
        ("Hello everyone", 1.0, "2024-01-02 10:00:00"),
        ("world cup final", 1.0, "2024-01-03 10:00:00"),
    ])
    let store = HistoryStore(dbPath: path)
    store.search(query: "world")

    #expect(store.records.count == 2)
}

@Test func paginationLoads50PerPage() throws {
    var rows: [(String, Double, String)] = []
    for i in 1...75 {
        rows.append(("Record \(i)", Double(i), "2024-01-01 10:00:00"))
    }
    let path = try makeTempDB(records: rows)
    let store = HistoryStore(dbPath: path)

    store.loadPage()
    #expect(store.records.count == 50)
    #expect(store.hasMore == true)

    store.loadNextPage()
    #expect(store.records.count == 75)
    #expect(store.hasMore == false)
}

@Test func emptyDatabaseReturnsEmptyList() throws {
    let path = try makeTempDB(records: [])
    let store = HistoryStore(dbPath: path)
    store.loadPage()

    #expect(store.records.isEmpty)
    #expect(store.hasMore == false)
}
