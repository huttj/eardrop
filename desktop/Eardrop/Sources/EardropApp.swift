import SwiftUI

@main
struct EardropApp: App {
    @StateObject private var recordingManager = RecordingManager()

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(manager: recordingManager)
        } label: {
            Image(systemName: recordingManager.isRecording ? "waveform.circle.fill" : "waveform.circle")
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(recordingManager.isRecording ? .red : .primary)
        }
        .menuBarExtraStyle(.window)
    }
}
