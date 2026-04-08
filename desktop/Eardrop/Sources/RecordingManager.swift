import Combine
import Foundation
import os.log

/// Orchestrates system audio + microphone capture into a recording session.
@MainActor
final class RecordingManager: ObservableObject {
    private let logger = Logger(subsystem: "com.eardrop", category: "RecordingManager")

    @Published var isRecording = false
    @Published var recordingDuration: TimeInterval = 0
    @Published var errorMessage: String?

    private let systemCapture = SystemAudioCapture()
    private let micCapture = MicrophoneCapture()
    private var timer: Timer?
    private var startTime: Date?

    /// Directory where recordings are saved (iCloud Drive > Eardrop > Inbox).
    var inboxURL: URL {
        // ~/Library/Mobile Documents/com~apple~CloudDocs/Eardrop/Inbox
        let icloud = FileManager.default.url(
            forUbiquityContainerIdentifier: nil
        )?.appendingPathComponent("Documents")

        // Fallback to iCloud Drive path directly if ubiquity container isn't available
        let base = icloud ?? FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Mobile Documents/com~apple~CloudDocs")

        let inbox = base
            .appendingPathComponent("Eardrop")
            .appendingPathComponent("Inbox")

        try? FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
        return inbox
    }

    /// Start recording both system audio and microphone.
    func startRecording() {
        guard !isRecording else { return }
        errorMessage = nil

        let timestamp = Self.timestamp()

        Task {
            do {
                let micURL = inboxURL.appendingPathComponent("\(timestamp)_mic.wav")
                let sysURL = inboxURL.appendingPathComponent("\(timestamp)_system.wav")

                // Start both captures concurrently
                async let micStart: () = micCapture.start(outputURL: micURL)
                async let sysStart: () = try systemCapture.start(outputURL: sysURL)

                try await micStart
                try await sysStart

                isRecording = true
                startTime = Date()
                startTimer()
                logger.info("Recording started: \(timestamp)")
            } catch {
                logger.error("Failed to start recording: \(error.localizedDescription)")
                errorMessage = error.localizedDescription
                // Clean up whichever started
                micCapture.stop()
                await systemCapture.stop()
            }
        }
    }

    /// Stop recording.
    func stopRecording() {
        guard isRecording else { return }

        Task {
            micCapture.stop()
            await systemCapture.stop()

            stopTimer()
            isRecording = false
            logger.info("Recording stopped (duration: \(self.recordingDuration, format: .fixed(precision: 0))s)")
        }
    }

    /// Toggle recording state.
    func toggle() {
        if isRecording {
            stopRecording()
        } else {
            startRecording()
        }
    }

    // MARK: - Timer

    private func startTimer() {
        recordingDuration = 0
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, let start = self.startTime else { return }
                self.recordingDuration = Date().timeIntervalSince(start)
            }
        }
    }

    private func stopTimer() {
        timer?.invalidate()
        timer = nil
    }

    // MARK: - Helpers

    private static func timestamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd_HHmm"
        return f.string(from: Date())
    }

    /// Format duration as HH:MM:SS.
    static func formatDuration(_ seconds: TimeInterval) -> String {
        let h = Int(seconds) / 3600
        let m = (Int(seconds) % 3600) / 60
        let s = Int(seconds) % 60

        if h > 0 {
            return String(format: "%d:%02d:%02d", h, m, s)
        } else {
            return String(format: "%d:%02d", m, s)
        }
    }
}
