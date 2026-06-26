#!/usr/bin/env python3
"""WZ Biên Bản - app menu-bar (macOS). Vỏ điều khiển nhẹ, gọi engine qua venv.

Nút trên thanh menu:
  ● Bắt đầu họp
  ■ Kết thúc & tạo biên bản
  Mở thư mục kết quả / Mở Claude để viết biên bản / Thoát

Engine (mlx-whisper, ffmpeg) nằm ở ~/wz-bien-ban/.venv (cài 1 lần). App chỉ điều phối.
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import rumps

HOME = Path.home()
DATA = HOME / "wz-bien-ban"
VENV_PY = DATA / ".venv" / "bin" / "python"
STATE = DATA / ".state.json"
OUTPUT = DATA / "output"
# Engine: khi đóng gói nằm ở _MEIPASS/engine; khi chạy từ repo nằm ở plugins/.../scripts
_here = Path(__file__).resolve().parent
_cands = []
if getattr(sys, "_MEIPASS", None):
    _cands.append(Path(sys._MEIPASS) / "engine")
_cands += [_here / "engine", _here.parent / "plugins" / "wz-bien-ban" / "scripts", _here]
ENGINE = next((c for c in _cands if (c / "wz.py").exists()), _cands[-1])
WZ = ENGINE / "wz.py"


def _engine(*args):
    """Gọi engine bằng python của venv. Trả (rc, output)."""
    try:
        r = subprocess.run([str(VENV_PY), str(WZ), *args],
                           capture_output=True, text=True, timeout=1800)
        return r.returncode, (r.stdout + r.stderr)
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def _recording():
    if not STATE.exists():
        return None
    try:
        st = json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001
        return None
    try:
        import os
        os.kill(st.get("pid", -1), 0)
        return st
    except OSError:
        return None


class WZApp(rumps.App):
    def __init__(self):
        super().__init__("Workzone Meeting Note", title="🎙️", quit_button=None)
        self.menu = [
            rumps.MenuItem("● Bắt đầu họp", callback=self.start),
            rumps.MenuItem("■ Kết thúc & tạo biên bản", callback=self.stop),
            None,
            rumps.MenuItem("Mở thư mục kết quả", callback=self.open_folder),
            rumps.MenuItem("Mở Claude để viết biên bản", callback=self.open_claude),
            None,
            rumps.MenuItem("Bật ghi tiếng trong máy", callback=self.system_audio_on),
            rumps.MenuItem("Tắt ghi tiếng trong máy", callback=self.system_audio_off),
            None,
            rumps.MenuItem("Trạng thái cài đặt", callback=self.check_setup),
            rumps.MenuItem("Thoát", callback=self.quit_app),
        ]
        self._busy = False
        self._installing = False
        rumps.Timer(self._tick, 2).start()
        if not VENV_PY.exists():
            self._installing = True
            threading.Thread(target=self._first_run_install, daemon=True).start()

    def _first_run_install(self):
        """Lần mở đầu: tự tải engine + model + đăng ký MCP (không cần cài tay)."""
        rumps.notification("Workzone Meeting Note", "Đang cài đặt lần đầu",
                           "Tải bộ nhận giọng nói (~3GB), chờ vài phút. Đừng tắt app.")
        try:
            subprocess.run(
                "curl -fsSL https://raw.githubusercontent.com/workzone-vn/"
                "wz-bien-ban/main/install.sh | bash",
                shell=True, timeout=3600,
            )
        except Exception:  # noqa: BLE001
            pass
        self._installing = False
        if VENV_PY.exists():
            rumps.notification("Workzone Meeting Note", "Cài xong ✓",
                               "Sẵn sàng. Bấm 'Bắt đầu họp' để ghi.")
        else:
            rumps.notification("Workzone Meeting Note", "Cài chưa xong",
                               "Mở Terminal chạy: curl -fsSL .../install.sh | bash")

    def _tick(self, _):
        st = _recording()
        if self._installing:
            self.title = "⏳ Cài..."
        elif st:
            mins = (time.time() - st["started"]) / 60
            self.title = f"🔴 {mins:.0f}′"
        elif self._busy:
            self.title = "⏳"
        else:
            self.title = "🎙️"

    def start(self, _):
        if self._installing:
            rumps.notification("Workzone Meeting Note", "Đang cài đặt lần đầu", "Chờ cài xong rồi ghi nhé.")
            return
        if not VENV_PY.exists():
            rumps.alert("Chưa cài đặt", "Chạy cài đặt trước (xem 'Trạng thái cài đặt').")
            return
        if _recording():
            rumps.notification("Workzone Meeting Note", "", "Đang ghi rồi - hãy kết thúc trước.")
            return
        rc, _out = _engine("record-start")
        if rc == 0:
            rumps.notification("Workzone Meeting Note", "Đang ghi cuộc họp",
                               "Bật loa ngoài nếu chưa cài BlackHole. Xong bấm 'Kết thúc'.")
        else:
            rumps.notification("Workzone Meeting Note", "Không bắt đầu được", _out[-180:])

    def stop(self, _):
        if not _recording():
            rumps.notification("Workzone Meeting Note", "", "Không có cuộc họp nào đang ghi.")
            return
        if self._busy:
            return
        self._busy = True
        rumps.notification("Workzone Meeting Note", "Đang xử lý", "Dừng ghi và tạo transcript...")
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _do_stop(self):
        rc, out = _engine("record-stop")
        name = None
        for line in out.splitlines():
            if line.startswith("OUTPUT_DIR="):
                name = Path(line.split("=", 1)[1]).name
        if rc != 0 or not name:
            self._busy = False
            rumps.notification("Workzone Meeting Note", "Có lỗi khi transcript", out[-180:])
            return
        # Tự viết biên bản + xuất PDF (Claude Code headless)
        rumps.notification("Workzone Meeting Note", "Đang viết biên bản...",
                           "Claude đang soạn biên bản và xuất PDF.")
        rc2, out2 = _engine("bienban", name)
        self._busy = False
        if rc2 == 0:
            rumps.notification("Workzone Meeting Note", "Xong ✓",
                               "Biên bản + PDF đã tạo và mở ra cho bạn.")
        elif "NO_CLAUDE" in out2 or rc2 == 2:
            rumps.notification("Workzone Meeting Note", "Transcript xong ✓",
                               "Chưa thấy Claude Code. Mở Claude và gõ: viết biên bản cuộc họp vừa rồi")
        else:
            rumps.notification("Workzone Meeting Note", "Transcript xong, biên bản lỗi",
                               out2[-160:])

    def open_folder(self, _):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(OUTPUT)], check=False)

    def open_claude(self, _):
        subprocess.run(["open", "-a", "Claude"], check=False)

    def system_audio_on(self, _):
        (DATA / ".system_audio").touch()
        rumps.alert(
            "Đã bật ghi tiếng trong máy",
            "Từ giờ app ghi được cả tiếng người khác trong cuộc họp (kể cả khi bạn đeo tai nghe), "
            "KHÔNG cần cài thêm gì.\n\n"
            "Lần ghi đầu tiên, macOS sẽ hỏi quyền 'Ghi màn hình & âm thanh' cho Workzone Meeting Note "
            "-> bấm Cho phép (chỉ 1 lần).")

    def system_audio_off(self, _):
        flag = DATA / ".system_audio"
        if flag.exists():
            flag.unlink()
        rumps.notification("Workzone Meeting Note", "Đã tắt ghi tiếng trong máy",
                           "Quay lại chỉ ghi qua mic.")

    def check_setup(self, _):
        if not VENV_PY.exists():
            rumps.alert("Chưa cài engine",
                        "Mở Terminal chạy:\ncurl -fsSL https://raw.githubusercontent.com/"
                        "workzone-vn/workzone-meeting-note/main/install.sh | bash")
            return
        rc, out = _engine("check")
        rumps.alert("Workzone Meeting Note", out.strip() or "OK")

    def quit_app(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    WZApp().run()
