#!/usr/bin/env python3
"""WZ Biên Bản - lõi engine transcript họp (chạy local, AI dùng Claude Code).

Các lệnh con:
    wz.py record-start [tên]     Bắt đầu ghi âm cuộc họp (chạy nền)
    wz.py record-stop            Dừng ghi + transcript + ghép -> in đường dẫn transcript
    wz.py pdf <tên>              Xuất biên bản + transcript ra PDF (cần bien-ban.md đã có)
    wz.py viewer <tên>           Tạo trang HTML xem transcript + biên bản
    wz.py diarize <tên>          Tách người nói (cần HF_TOKEN)
    wz.py status                 Xem đang ghi cuộc nào không
    wz.py check                  Kiểm tra đã cài đủ chưa

Dữ liệu lưu tại ~/wz-bien-ban/ (đổi bằng biến môi trường WZ_DATA_DIR).
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

DATA = Path(os.environ.get("WZ_DATA_DIR", str(Path.home() / "wz-bien-ban")))
OUTPUT = DATA / "output"
STATE = DATA / ".state.json"
HERE = Path(__file__).resolve().parent
AUDIO_DEV = os.environ.get("WZ_AUDIO_DEV", ":0")  # :0 = mic; đổi nếu cài BlackHole
MODEL_HQ = "mlx-community/whisper-large-v3-mlx"
MODEL_TURBO = "mlx-community/whisper-large-v3-turbo"


def ensure_ffmpeg():
    """Đảm bảo có 'ffmpeg' trong PATH. Nếu máy chưa có, dùng bản đóng gói qua pip
    (imageio-ffmpeg) - tạo symlink tên 'ffmpeg' để cả mlx-whisper cũng tìm thấy.
    Nhờ vậy khách KHÔNG cần tự cài ffmpeg ngoài."""
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg
    except ImportError:
        return  # install.sh sẽ cài; nếu chưa có thì để lỗi rõ ràng ở chỗ dùng
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    bindir = DATA / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    link = bindir / "ffmpeg"
    if not link.exists():
        try:
            link.symlink_to(exe)
        except OSError:
            shutil.copy2(exe, link)
            link.chmod(0o755)
    os.environ["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"


def _ts(sec):
    h, m, s = int(sec // 3600), int((sec % 3600) // 60), int(sec % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _safe_name(name):
    name = (name or "").strip()
    if not name:
        name = "hop-" + time.strftime("%Y%m%d-%H%M")
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in name).strip("-")


# ---------- GHI ÂM ----------

def record_start(name):
    DATA.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        st = json.loads(STATE.read_text())
        if st.get("pid") and _alive(st["pid"]):
            print(f"Đang ghi cuộc '{st['name']}' rồi. Gõ 'kết thúc họp' để dừng trước đã.")
            return 1
    name = _safe_name(name)
    out_dir = OUTPUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    started_ts = time.time()
    # Lưu thời điểm bắt đầu họp (lúc bấm Bắt đầu) - survive khi record-stop xoá STATE
    (out_dir / "meeting.json").write_text(json.dumps({"started": started_ts}), encoding="utf-8")
    wav = out_dir / "audio.16k.wav"
    log = open(out_dir / "_record.log", "w")
    pids, mode = [], "mic"

    # Tiền kiểm: thu thử mic ~1.2s, nếu im lặng tuyệt đối -> cảnh báo ngay (đừng mất cả buổi)
    mic_dev = os.environ.get("WZ_AUDIO_DEV") or f":{_mic_index()}"
    lvl = _probe_level(mic_dev)
    mic_silent = lvl is not None and lvl <= -80.0

    if _system_mode():
        # Tiếng hệ thống (ScreenCaptureKit) + mic (ffmpeg) song song, trộn khi dừng
        mode = "system"
        sysp = subprocess.Popen([str(_syscap_path()), str(out_dir / "system.wav")],
                                stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        micp = subprocess.Popen(_mic_cmd(out_dir / "mic.wav"),
                                stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        pids = [sysp.pid, micp.pid]
    else:
        proc = subprocess.Popen(_mic_cmd(wav), stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        pids = [proc.pid]

    STATE.write_text(json.dumps({"name": name, "pid": pids[0], "pids": pids,
                                 "mode": mode, "wav": str(wav), "started": started_ts}))
    print(f"🔴 ĐANG GHI cuộc họp: {name}" + (" (mic + tiếng hệ thống)" if mode == "system" else ""))
    if mic_silent:
        print("WARN_SILENT: ⚠️ Mic KHÔNG có tín hiệu (thiết bị im lặng). "
              "Kiểm tra: mic có bị tắt? đúng mic chưa? đã cấp quyền Micro chưa? "
              "Nên DỪNG, sửa, rồi ghi lại để khỏi mất buổi họp.")
    print("   Họp xong gõ: kết thúc họp")
    return 0


def _list_audio():
    """Trả [(index, name)] các thiết bị audio đầu vào của avfoundation."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation",
                        "-list_devices", "true", "-i", ""],
                       capture_output=True, text=True)
    out = r.stderr + r.stdout
    devs, in_audio = [], False
    for line in out.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if in_audio:
            if "AVFoundation video devices" in line:
                break
            m = re.search(r"\[(\d+)\]\s*(.+?)\s*$", line)
            if m:
                devs.append((m.group(1), m.group(2)))
    return devs


def _mic_index(devs=None):
    """Index mic thật (bỏ qua thiết bị ảo). Mặc định thiết bị đầu hợp lệ."""
    devs = devs or _list_audio()
    for idx, name in devs:
        low = name.lower()
        if "blackhole" not in low and "aggregate" not in low:
            return idx
    return devs[0][0] if devs else "0"


def _probe_level(dev, secs=1.2):
    """Đo mức âm lượng trung bình (dB) của 1 thiết bị trong ~1.2s. None nếu lỗi.
    Dùng để cảnh báo SỚM nếu đang thu phải thiết bị im lặng (sai mic / mic tắt)."""
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-i", dev,
                            "-t", str(secs), "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=15)
        for line in (r.stderr + r.stdout).splitlines():
            m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", line)
            if m:
                return float(m.group(1))
    except Exception:  # noqa: BLE001
        pass
    return None


def _syscap_path():
    """Đường dẫn binary bắt tiếng hệ thống (ScreenCaptureKit). None nếu không có."""
    for c in [HERE / "wz-syscap",
              HERE.parent / "native" / "wz-syscap",
              DATA / "engine" / "wz-syscap"]:
        if c.exists():
            return c
    return None


def _mic_cmd(wav):
    """Lệnh ffmpeg ghi mic -> wav 16k mono."""
    mic = os.environ.get("WZ_AUDIO_DEV") or f":{_mic_index()}"
    return ["ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-f", "avfoundation", "-i", mic,
            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]


def _system_mode():
    return (DATA / ".system_audio").exists() and _syscap_path() is not None


def _alive(pid):
    # Chặn pid không hợp lệ: os.kill(-1, 0) KHÔNG raise (pid -1 = "mọi tiến trình")
    # nên nếu .state.json thiếu/hỏng key pid sẽ báo nhầm "đang ghi". Phải guard.
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def record_stop(turbo=False):
    if not STATE.exists():
        print("Không có cuộc họp nào đang ghi.")
        return 1
    st = json.loads(STATE.read_text())
    name, wav = st["name"], Path(st["wav"])
    pids = st.get("pids") or [st.get("pid")]
    for pid in pids:
        if pid and _alive(pid):
            os.kill(pid, signal.SIGINT)
    for _ in range(60):
        if not any(p and _alive(p) for p in pids):
            break
        time.sleep(0.1)
    STATE.unlink(missing_ok=True)

    out_dir = OUTPUT / name
    if st.get("mode") == "system":
        # Trộn tiếng hệ thống + mic -> audio.16k.wav
        sysw, micw = out_dir / "system.wav", out_dir / "mic.wav"
        ins = [p for p in (sysw, micw) if p.exists() and p.stat().st_size > 1000]
        if len(ins) == 2:
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-i", str(sysw), "-i", str(micw),
                            "-filter_complex", "amix=inputs=2:duration=longest:normalize=0",
                            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=False)
        elif ins:
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-i", str(ins[0]), "-ac", "1", "-ar", "16000",
                            "-c:a", "pcm_s16le", str(wav)], check=False)

    size = wav.stat().st_size if wav.exists() else 0
    print(f"⏹  Đã dừng ghi: {name} ({size // 1024} KB)")
    if size < 5000:
        print("File ghi quá nhỏ - có thể chưa cấp quyền micro/ghi màn hình.")
        return 1
    print("Đang transcript (chạy local)...")
    _transcribe(name, turbo)
    _merge(name)
    out_dir = OUTPUT / name
    print(f"\n✅ Transcript xong -> {out_dir}/transcript.speakers.txt")
    print(f"OUTPUT_DIR={out_dir}")
    return 0


# ---------- TRANSCRIPT ----------

def _transcribe(name, turbo=False):
    import mlx_whisper
    out_dir = OUTPUT / name
    wav = out_dir / "audio.16k.wav"
    model = MODEL_TURBO if turbo else MODEL_HQ
    result = mlx_whisper.transcribe(str(wav), path_or_hf_repo=model,
                                    language="vi", word_timestamps=True, verbose=False)
    segs = [{"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in result.get("segments", [])]
    (out_dir / "transcript.raw.json").write_text(
        json.dumps(segs, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"[{_ts(s['start'])} -> {_ts(s['end'])}] {s['text']}" for s in segs]
    (out_dir / "transcript.raw.txt").write_text("\n".join(lines), encoding="utf-8")
    return segs


def _speaker_for(seg, turns):
    best, best_ov = None, 0.0
    for t in turns:
        ov = min(seg["end"], t["end"]) - max(seg["start"], t["start"])
        if ov > best_ov:
            best_ov, best = ov, t["speaker"]
    return best


def _merge(name):
    out_dir = OUTPUT / name
    segs = json.loads((out_dir / "transcript.raw.json").read_text(encoding="utf-8"))
    diar = out_dir / "diarization.json"
    turns = json.loads(diar.read_text(encoding="utf-8")) if diar.exists() else []
    lines, last = [], None
    for s in segs:
        spk = _speaker_for(s, turns) if turns else None
        prefix = ""
        if spk and spk != last:
            prefix = f"\n[{spk}] "
            last = spk
        lines.append(f"{prefix}({_ts(s['start'])}) {s['text']}")
    (out_dir / "transcript.speakers.txt").write_text("\n".join(lines), encoding="utf-8")


def diarize(name, speakers=None):
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    env = DATA / ".env"
    if not token and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("HF_TOKEN="):
                token = line.split("=", 1)[1].strip()
    if not token:
        print("Chưa bật tách người nói. Cần HF_TOKEN. Xem lệnh /biên-bản cài-đặt.")
        return 1
    out_dir = OUTPUT / name
    wav = out_dir / "audio.16k.wav"
    try:
        import soundfile as sf
        import torch
        from pyannote.audio import Pipeline
    except ImportError:
        print("Thiếu thư viện tách người nói. Cài thêm (1 lần):\n"
              "  source ~/wz-bien-ban/.venv/bin/activate\n"
              '  uv pip install torch "pyannote.audio>=3.1"')
        return 1
    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
    if torch.backends.mps.is_available():
        pipe.to(torch.device("mps"))
    data, sr = sf.read(str(wav), dtype="float32")
    wf = torch.from_numpy(data).unsqueeze(0)
    kw = {"num_speakers": speakers} if speakers else {}
    dz = pipe({"waveform": wf, "sample_rate": sr}, **kw)
    turns = [{"start": float(s.start), "end": float(s.end), "speaker": spk}
             for s, _, spk in dz.itertracks(yield_label=True)]
    (out_dir / "diarization.json").write_text(
        json.dumps(turns, ensure_ascii=False, indent=2), encoding="utf-8")
    _merge(name)
    print(f"Tách người nói xong: {len({t['speaker'] for t in turns})} người.")
    return 0


# ---------- PDF ----------

def export_pdf(name):
    from render import build_print_html
    out_dir = OUTPUT / name
    if not (out_dir / "bien-ban.md").exists():
        print("Chưa có bien-ban.md. Claude cần viết biên bản trước.")
        return 1
    html_path = build_print_html(out_dir)
    pdf_path = out_dir / "bien-ban.pdf"
    chrome = None
    for c in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]:
        if Path(c).exists():
            chrome = c
            break
    if not chrome:
        # Không có trình duyệt Chromium -> vẫn ra HTML để in tay (không fail)
        from render import build_viewer_html
        v = build_viewer_html(out_dir)
        print(f"Chưa có Chrome để tự xuất PDF. Đã tạo trang xem: {v}")
        print("Mở trang đó rồi In (Cmd+P) -> Save as PDF nếu cần file PDF.")
        subprocess.run(["open", str(v)], check=False)
        return 0
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                    "--no-pdf-header-footer", "--print-to-pdf-no-header",
                    f"--print-to-pdf={pdf_path}", f"file://{html_path}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    # Xoá file print.html trung gian để không gây nhầm (mở nó bằng trình duyệt sẽ
    # thêm header/footer của trình duyệt). Chỉ giữ bien-ban.pdf sạch.
    try:
        Path(html_path).unlink()
    except OSError:
        pass
    if pdf_path.exists():
        print(f"✅ PDF: {pdf_path}")
        subprocess.run(["open", str(pdf_path)], check=False)
        return 0
    print("Render PDF thất bại.")
    return 1


def make_viewer(name):
    from render import build_viewer_html
    out_dir = OUTPUT / name
    p = build_viewer_html(out_dir)
    print(f"✅ Trang xem: {p}")
    subprocess.run(["open", str(p)], check=False)
    return 0


def _claude_bin():
    """Tìm CLI 'claude' (app mở từ Finder có PATH hẹp)."""
    c = shutil.which("claude")
    if c:
        return c
    for p in [Path.home() / ".local/bin/claude", Path("/opt/homebrew/bin/claude"),
              Path("/usr/local/bin/claude")]:
        if p.exists():
            return str(p)
    return None


def write_bienban(name):
    """Tự viết biên bản từ transcript bằng Claude Code headless (subscription của user), rồi xuất PDF."""
    out_dir = OUTPUT / name
    tx_file = out_dir / "transcript.speakers.txt"
    if not tx_file.exists():
        print("Chưa có transcript.")
        return 1
    claude = _claude_bin()
    if not claude:
        print("NO_CLAUDE")  # app sẽ bảo user tự mở Claude
        return 2
    tx = tx_file.read_text(encoding="utf-8")
    gloss = (HERE / "glossary.yaml")
    glossary = gloss.read_text(encoding="utf-8") if gloss.exists() else ""
    try:
        import render
        started = render.fmt_meeting_time(out_dir)
    except Exception:  # noqa: BLE001
        started = ""
    time_line = (f"THỜI GIAN BẮT ĐẦU HỌP (dùng đúng giá trị này): {started}\n\n"
                 if started else "")
    prompt = (
        "Bạn là thư ký ghi biên bản họp. Dưới đây là transcript thô (tiếng Việt, có thể sai "
        "chính tả tên riêng/thuật ngữ) của một cuộc họp.\n\n"
        f"{time_line}"
        f"GLOSSARY (sửa tên riêng/thuật ngữ theo đây nếu gặp):\n{glossary}\n\n"
        "YÊU CẦU: Viết BIÊN BẢN HỌP hoàn chỉnh bằng tiếng Việt, định dạng Markdown, gồm:\n"
        "# Tiêu đề (suy ra chủ đề)\n"
        "Ngay dưới tiêu đề ghi dòng: **Thời gian:** <thời gian bắt đầu họp ở trên>\n"
        "## Tóm tắt (3-6 gạch đầu dòng)\n"
        "## Nội dung chính (theo chủ đề, không chép lại từng câu)\n"
        "## Quyết định\n"
        "## Action items (bảng Markdown: | Việc | Người phụ trách | Deadline |)\n"
        "QUY ƯỚC: KHÔNG dùng gạch dài (em-dash); heading từ 2 câu thêm <br> sau câu đầu; "
        "bỏ các đoạn nhiễu (ký tự lặp vô nghĩa). CHỈ XUẤT MARKDOWN BIÊN BẢN, không thêm lời dẫn.\n\n"
        f"TRANSCRIPT:\n{tx}\n"
    )
    env = dict(os.environ)
    env["PATH"] = f"{Path(claude).parent}{os.pathsep}{env.get('PATH','')}"
    print("Đang viết biên bản bằng Claude...")
    # Truyền prompt qua stdin thay vì argv: transcript họp dài có thể vượt
    # ARG_MAX (~1MB) nếu nhồi vào 1 đối số dòng lệnh -> "Argument list too long".
    r = subprocess.run([claude, "-p"], input=prompt, capture_output=True, text=True,
                       timeout=900, cwd=str(DATA), env=env)
    md = (r.stdout or "").strip()
    if not md:
        print("Claude không trả về nội dung:", (r.stderr or "")[-200:])
        return 1
    # Ép bỏ gạch dài em-dash (quy ước cứng), giữ en-dash cho dải số
    md = md.replace(" — ", " - ").replace("—", "-")
    (out_dir / "bien-ban.md").write_text(md, encoding="utf-8")
    print("✅ Đã viết biên bản. Xuất PDF...")
    export_pdf(name)
    return 0


# ---------- TIỆN ÍCH ----------

def status():
    if STATE.exists():
        st = json.loads(STATE.read_text())
        if _alive(st.get("pid", -1)):
            mins = (time.time() - st["started"]) / 60
            print(f"🔴 Đang ghi: {st['name']} ({mins:.1f} phút)")
            return 0
    print("Không có cuộc họp nào đang ghi.")
    return 0


def check():
    ok = True
    for mod in ["mlx_whisper"]:
        try:
            __import__(mod)
        except ImportError:
            print(f"Thiếu: {mod}"); ok = False
    if not shutil.which("ffmpeg"):
        print("Thiếu: ffmpeg (sẽ tự dùng bản đóng gói imageio-ffmpeg khi chạy)")
    print("✅ Sẵn sàng." if ok else "Chưa đủ - chạy /cai-dat.")
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return 1
    cmd, rest = args[0], args[1:]
    if cmd in ("record-start", "record-stop", "check"):
        ensure_ffmpeg()  # đảm bảo ffmpeg sẵn (dùng bản pip nếu máy chưa có)
    if cmd == "record-start":
        return record_start(rest[0] if rest else None)
    if cmd == "record-stop":
        return record_stop("--turbo" in rest)
    if cmd == "bienban":
        return write_bienban(rest[0])
    if cmd == "pdf":
        return export_pdf(rest[0])
    if cmd == "viewer":
        return make_viewer(rest[0])
    if cmd == "diarize":
        n = rest[0]
        spk = int(rest[1]) if len(rest) > 1 else None
        return diarize(n, spk)
    if cmd == "status":
        return status()
    if cmd == "check":
        return check()
    print(f"Lệnh không hợp lệ: {cmd}\n{__doc__}")
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    raise SystemExit(main())
