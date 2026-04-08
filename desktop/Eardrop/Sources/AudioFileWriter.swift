import AVFoundation
import os.log

/// Thread-safe writer for audio data to a WAV file.
final class AudioFileWriter {
    private let logger = Logger(subsystem: "com.eardrop", category: "AudioFileWriter")
    private var audioFile: AVAudioFile?
    private let queue = DispatchQueue(label: "com.eardrop.filewriter")
    let url: URL
    let format: AVAudioFormat

    init(url: URL, format: AVAudioFormat) throws {
        self.url = url
        self.format = format
        self.audioFile = try AVAudioFile(
            forWriting: url,
            settings: format.settings,
            commonFormat: .pcmFormatFloat32,
            interleaved: false
        )
        logger.info("Opened audio file for writing: \(url.lastPathComponent)")
    }

    /// Write a PCM buffer to the file. Thread-safe.
    func write(_ buffer: AVAudioPCMBuffer) {
        queue.sync {
            guard let file = audioFile else { return }
            do {
                try file.write(from: buffer)
            } catch {
                logger.error("Failed to write audio buffer: \(error.localizedDescription)")
            }
        }
    }

    /// Close the file and finalize.
    func close() {
        queue.sync {
            audioFile = nil
            logger.info("Closed audio file: \(url.lastPathComponent)")
        }
    }
}

// MARK: - CMSampleBuffer conversion

import CoreMedia

extension AudioFileWriter {
    /// Convert a CMSampleBuffer (from ScreenCaptureKit) to AVAudioPCMBuffer.
    static func pcmBuffer(from sampleBuffer: CMSampleBuffer) -> AVAudioPCMBuffer? {
        guard let formatDescription = sampleBuffer.formatDescription,
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(formatDescription)
        else {
            return nil
        }

        guard let format = AVAudioFormat(streamDescription: asbd) else {
            return nil
        }

        let numFrames = CMSampleBufferGetNumSamples(sampleBuffer)
        guard let pcmBuffer = AVAudioPCMBuffer(
            pcmFormat: format,
            frameCapacity: AVAudioFrameCount(numFrames)
        ) else {
            return nil
        }

        pcmBuffer.frameLength = AVAudioFrameCount(numFrames)

        let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer,
            at: 0,
            frameCount: Int32(numFrames),
            into: pcmBuffer.mutableAudioBufferList
        )

        guard status == noErr else {
            return nil
        }

        return pcmBuffer
    }
}
