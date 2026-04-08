import AVFoundation
import os.log
import ScreenCaptureKit

/// Captures system audio output using ScreenCaptureKit.
/// Works regardless of which output device is selected.
final class SystemAudioCapture: NSObject {
    private let logger = Logger(subsystem: "com.eardrop", category: "SystemAudio")
    private var stream: SCStream?
    private var writer: AudioFileWriter?
    private let audioQueue = DispatchQueue(label: "com.eardrop.systemaudio")

    /// Whether system audio capture is currently active.
    private(set) var isCapturing = false

    /// Request screen recording permission and start capturing system audio.
    func start(outputURL: URL) async throws {
        guard !isCapturing else { return }

        // 1. Get available content (triggers permission prompt if needed)
        let content = try await SCShareableContent.excludingDesktopWindows(
            false, onScreenWindowsOnly: false
        )

        guard let display = content.displays.first else {
            throw CaptureError.noDisplay
        }

        // 2. Configure for audio-only capture
        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = 48_000
        config.channelCount = 1

        // Minimal video (required by API but we don't use it)
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1) // 1 fps minimum

        // 3. Filter: capture all audio from the display
        let filter = SCContentFilter(
            display: display,
            excludingApplications: [],
            exceptingWindows: []
        )

        // 4. Create the audio file writer
        let format = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: 48_000,
            channels: 1,
            interleaved: false
        )!
        writer = try AudioFileWriter(url: outputURL, format: format)

        // 5. Create and start the stream
        let stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: audioQueue)
        try await stream.startCapture()

        self.stream = stream
        isCapturing = true
        logger.info("System audio capture started")
    }

    /// Stop capturing system audio.
    func stop() async {
        guard isCapturing, let stream = stream else { return }

        do {
            try await stream.stopCapture()
        } catch {
            logger.error("Error stopping stream: \(error.localizedDescription)")
        }

        writer?.close()
        writer = nil
        self.stream = nil
        isCapturing = false
        logger.info("System audio capture stopped")
    }
}

// MARK: - SCStreamOutput

extension SystemAudioCapture: SCStreamOutput {
    func stream(
        _ stream: SCStream,
        didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
        of type: SCStreamOutputType
    ) {
        guard type == .audio else { return }

        if let pcmBuffer = AudioFileWriter.pcmBuffer(from: sampleBuffer) {
            writer?.write(pcmBuffer)
        }
    }
}

// MARK: - SCStreamDelegate

extension SystemAudioCapture: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        logger.error("System audio stream stopped with error: \(error.localizedDescription)")
        isCapturing = false
    }
}

// MARK: - Errors

enum CaptureError: LocalizedError {
    case noDisplay
    case noPermission

    var errorDescription: String? {
        switch self {
        case .noDisplay:
            return "No display found for audio capture."
        case .noPermission:
            return "Screen recording permission is required to capture system audio."
        }
    }
}
