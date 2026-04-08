import AVFoundation
import os.log

/// Captures microphone input using AVAudioEngine.
final class MicrophoneCapture {
    private let logger = Logger(subsystem: "com.eardrop", category: "Microphone")
    private let engine = AVAudioEngine()
    private var writer: AudioFileWriter?

    /// Whether microphone capture is currently active.
    private(set) var isCapturing = false

    /// Request microphone permission and start capturing.
    func start(outputURL: URL) async throws {
        guard !isCapturing else { return }

        // 1. Request microphone permission
        let granted = await AVCaptureDevice.requestAccess(for: .audio)
        guard granted else {
            throw MicError.noPermission
        }

        // 2. Get input format and create a writer at our target format
        let inputNode = engine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)

        let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: 48_000,
            channels: 1,
            interleaved: false
        )!

        writer = try AudioFileWriter(url: outputURL, format: targetFormat)

        // 3. Install a tap on the input node
        // If input sample rate differs from 48kHz, we need a converter
        if inputFormat.sampleRate != targetFormat.sampleRate ||
           inputFormat.channelCount != targetFormat.channelCount {
            // Use a converter
            guard let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
                throw MicError.formatConversionFailed
            }

            inputNode.installTap(onBus: 0, bufferSize: 4096, format: inputFormat) {
                [weak self] buffer, _ in
                self?.convertAndWrite(buffer: buffer, converter: converter, targetFormat: targetFormat)
            }
        } else {
            // Formats match, write directly
            inputNode.installTap(onBus: 0, bufferSize: 4096, format: inputFormat) {
                [weak self] buffer, _ in
                self?.writer?.write(buffer)
            }
        }

        // 4. Start the engine
        try engine.start()
        isCapturing = true
        logger.info("Microphone capture started (input: \(inputFormat.sampleRate)Hz \(inputFormat.channelCount)ch)")
    }

    /// Stop capturing microphone input.
    func stop() {
        guard isCapturing else { return }

        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        writer?.close()
        writer = nil
        isCapturing = false
        logger.info("Microphone capture stopped")
    }

    // MARK: - Format conversion

    private func convertAndWrite(
        buffer: AVAudioPCMBuffer,
        converter: AVAudioConverter,
        targetFormat: AVAudioFormat
    ) {
        let frameCount = AVAudioFrameCount(
            Double(buffer.frameLength) * targetFormat.sampleRate / buffer.format.sampleRate
        )
        guard let outputBuffer = AVAudioPCMBuffer(
            pcmFormat: targetFormat,
            frameCapacity: frameCount
        ) else { return }

        var error: NSError?
        var consumed = false
        converter.convert(to: outputBuffer, error: &error) { _, outStatus in
            if consumed {
                outStatus.pointee = .noDataNow
                return nil
            }
            consumed = true
            outStatus.pointee = .haveData
            return buffer
        }

        if error == nil && outputBuffer.frameLength > 0 {
            writer?.write(outputBuffer)
        }
    }
}

// MARK: - Errors

enum MicError: LocalizedError {
    case noPermission
    case formatConversionFailed

    var errorDescription: String? {
        switch self {
        case .noPermission:
            return "Microphone permission is required to record your voice."
        case .formatConversionFailed:
            return "Failed to set up audio format conversion."
        }
    }
}
