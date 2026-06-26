// wz-syscap - bắt TIẾNG HỆ THỐNG (system audio) bằng ScreenCaptureKit, ghi ra WAV.
// Không cần BlackHole. Chỉ cần quyền "Ghi màn hình & âm thanh" 1 lần.
//   wz-syscap <đường-dẫn-output.wav>
//   Dừng: gửi SIGINT (Ctrl+C / kill -INT)
import ScreenCaptureKit
import AVFoundation
import Foundation

extension CMSampleBuffer {
    func toPCMBuffer(format: AVAudioFormat) -> AVAudioPCMBuffer? {
        let n = AVAudioFrameCount(CMSampleBufferGetNumSamples(self))
        guard n > 0, let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: n) else { return nil }
        pcm.frameLength = n
        let st = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            self, at: 0, frameCount: Int32(n), into: pcm.mutableAudioBufferList)
        return st == noErr ? pcm : nil
    }
}

@available(macOS 13.0, *)
final class Cap: NSObject, SCStreamOutput, SCStreamDelegate {
    let outURL: URL
    var file: AVAudioFile?
    var stream: SCStream?
    let q = DispatchQueue(label: "wz.syscap.audio")

    init(_ url: URL) { self.outURL = url }

    func start() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else {
            FileHandle.standardError.write("Không tìm thấy màn hình.\n".data(using: .utf8)!)
            exit(2)
        }
        let filter = SCContentFilter(display: display, excludingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.capturesAudio = true
        cfg.sampleRate = 48000
        cfg.channelCount = 2
        cfg.width = 2; cfg.height = 2            // video tối thiểu (SCStream yêu cầu)
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        let s = SCStream(filter: filter, configuration: cfg, delegate: self)
        try s.addStreamOutput(self, type: .audio, sampleHandlerQueue: q)
        try await s.startCapture()
        self.stream = s
        FileHandle.standardError.write("WZ_SYSCAP_STARTED\n".data(using: .utf8)!)
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sb.isValid, sb.dataReadiness == .ready else { return }
        guard let fd = sb.formatDescription,
              var asbd = fd.audioStreamBasicDescription.map({ $0 }),
              let fmt = AVAudioFormat(streamDescription: &asbd),
              let pcm = sb.toPCMBuffer(format: fmt) else { return }
        if file == nil {
            file = try? AVAudioFile(forWriting: outURL, settings: fmt.settings,
                                    commonFormat: fmt.commonFormat, interleaved: fmt.isInterleaved)
        }
        try? file?.write(from: pcm)
    }

    func stop() {
        stream?.stopCapture(completionHandler: { _ in })
        file = nil   // flush + đóng file
    }
}

guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write("Dùng: wz-syscap <output.wav>\n".data(using: .utf8)!)
    exit(1)
}
let url = URL(fileURLWithPath: CommandLine.arguments[1])

if #available(macOS 13.0, *) {
    let cap = Cap(url)
    Task {
        do { try await cap.start() }
        catch {
            FileHandle.standardError.write("Lỗi bắt tiếng hệ thống: \(error)\n".data(using: .utf8)!)
            exit(3)
        }
    }
    signal(SIGINT, SIG_IGN)
    signal(SIGTERM, SIG_IGN)
    let onStop: () -> Void = { cap.stop(); DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { exit(0) } }
    var signalSources: [DispatchSourceSignal] = []
    for s in [SIGINT, SIGTERM] {
        let src = DispatchSource.makeSignalSource(signal: s, queue: .main)
        src.setEventHandler(handler: onStop)
        src.resume()
        signalSources.append(src)
    }
    RunLoop.main.run()
} else {
    FileHandle.standardError.write("Cần macOS 13 trở lên.\n".data(using: .utf8)!)
    exit(4)
}
