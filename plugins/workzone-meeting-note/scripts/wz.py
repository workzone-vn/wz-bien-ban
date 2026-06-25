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
    wav = out_dir / "audio.16k.wav"
    log = out_dir / "_record.log"
    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "warning",
         "-f", "avfoundation", "-i", AUDIO_DEV,
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
        stdout=open(log, "w"), stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    STATE.write_text(json.dumps({"name": name, "pid": proc.pid,
                                 "wav": str(wav), "started": time.time()}))
    print(f"🔴 ĐANG GHI cuộc họp: {name}")
    print("   Họp xong gõ: kết thúc họp")
    return 0


def _alive(pid):
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
    pid, name, wav = st["pid"], st["name"], Path(st["wav"])
    if _alive(pid):
        os.kill(pid, signal.SIGINT)
        for _ in range(50):
            if not _alive(pid):
                break
            time.sleep(0.1)
    STATE.unlink(missing_ok=True)
    size = wav.stat().st_size if wav.exists() else 0
    print(f"⏹  Đã dừng ghi: {name} ({size // 1024} KB)")
    if size < 5000:
        print("File ghi quá nhỏ - có thể chưa cấp quyền micro cho terminal.")
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
    import soundfile as sf
    import torch
    from pyannote.audio import Pipeline
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
                    "--print-to-pdf-no-header", f"--print-to-pdf={pdf_path}",
                    f"file://{html_path}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
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
