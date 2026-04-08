import SwiftUI

struct MenuBarView: View {
    @ObservedObject var manager: RecordingManager

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Status
            if manager.isRecording {
                HStack(spacing: 6) {
                    Circle()
                        .fill(.red)
                        .frame(width: 8, height: 8)
                    Text("Recording")
                        .font(.headline)
                    Spacer()
                    Text(RecordingManager.formatDuration(manager.recordingDuration))
                        .font(.system(.body, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("Eardrop")
                    .font(.headline)
            }

            Divider()

            // Record button
            Button(action: { manager.toggle() }) {
                HStack {
                    Image(systemName: manager.isRecording ? "stop.circle.fill" : "record.circle")
                        .foregroundStyle(manager.isRecording ? .red : .primary)
                    Text(manager.isRecording ? "Stop Recording" : "Start Recording")
                }
            }
            .keyboardShortcut("r", modifiers: [.command, .shift])

            // Error message
            if let error = manager.errorMessage {
                Divider()
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(3)
            }

            Divider()

            // Open inbox folder
            Button("Open Recordings Folder") {
                NSWorkspace.shared.open(manager.inboxURL)
            }

            Divider()

            Button("Quit Eardrop") {
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q")
        }
        .padding(4)
        .frame(width: 240)
    }
}
