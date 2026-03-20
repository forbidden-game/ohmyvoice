import SwiftUI
import AppKit

public struct HistoryView: View {
    @ObservedObject var store: HistoryStore
    @ObservedObject var bridge: IPCBridge

    @State private var searchText = ""
    @State private var showClearConfirm = false

    public init(store: HistoryStore, bridge: IPCBridge) {
        self.store = store
        self.bridge = bridge
    }

    public var body: some View {
        Group {
            if store.records.isEmpty && searchText.isEmpty {
                ContentUnavailableView(
                    "暂无转写记录",
                    systemImage: "mic.slash",
                    description: Text("开始录音后，转写记录会显示在这里")
                )
            } else {
                List {
                    ForEach(store.records) { record in
                        RecordRow(record: record)
                            .onAppear {
                                if record.id == store.records.last?.id && store.hasMore {
                                    store.loadNextPage()
                                }
                            }
                    }
                }
                .listStyle(.inset)
            }
        }
        .searchable(text: $searchText, prompt: "搜索转写记录...")
        .onChange(of: searchText) { _, query in
            if query.isEmpty {
                store.loadPage()
            } else {
                store.search(query: query)
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button("清空全部") {
                    showClearConfirm = true
                }
                .disabled(store.records.isEmpty)
            }
        }
        .confirmationDialog("确认清空所有转写记录？", isPresented: $showClearConfirm, titleVisibility: .visible) {
            Button("清空全部", role: .destructive) {
                bridge.send(.clearHistory)
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("此操作无法撤销。")
        }
        .frame(width: 520)
        .frame(minHeight: 400)
        .background(.ultraThinMaterial)
        .onAppear {
            bridge.send(.ready)
            store.loadPage()
        }
    }
}

// MARK: - RecordRow

private struct RecordRow: View {
    let record: TranscriptionRecord
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(expanded ? record.text : record.preview)
                .lineLimit(expanded ? nil : 2)
                .font(.body)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        expanded.toggle()
                    }
                }

            HStack(spacing: 0) {
                Text(record.createdAt)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(" · ")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(record.durationDisplay)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Spacer()

                Button {
                    let pb = NSPasteboard.general
                    pb.clearContents()
                    pb.setString(record.text, forType: .string)
                } label: {
                    Image(systemName: "doc.on.doc")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
