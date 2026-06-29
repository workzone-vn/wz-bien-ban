#!/usr/bin/env bash
# WZ Biên Bản - CÀI 1 PHÁT (Claude Code + Claude Desktop). Không cần cài gì ngoài.
#   curl -fsSL https://raw.githubusercontent.com/workzone-vn/workzone-meeting-note/main/install.sh | bash
set -e
DATA="${WZ_DATA_DIR:-$HOME/wz-bien-ban}"
RAW="https://raw.githubusercontent.com/workzone-vn/workzone-meeting-note/main"
mkdir -p "$DATA/output" "$DATA/engine"

echo "=================================================="
echo "   Cài đặt WZ Biên Bản"
echo "=================================================="

# 1. Môi trường Python + ffmpeg đóng gói + model (cho cả 3 mặt: plugin/MCP/app)
if ! command -v uv >/dev/null 2>&1; then
  echo "[1/4] Cài uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "[1/4] uv OK"
fi
uv venv --python 3.12 "$DATA/.venv" >/dev/null 2>&1 || true
source "$DATA/.venv/bin/activate"
echo "[2/4] Cài thư viện + tải model Whisper large-v3 (~3GB, lần đầu)..."
# Pin version: tránh một bản upstream breaking làm mọi máy cài mới hỏng.
uv pip install --quiet "mlx-whisper==0.4.3" "soundfile==0.14.0" "imageio-ffmpeg==0.6.0" "mcp[cli]==1.28.0"
# Tách người nói (diarize) cần torch + pyannote.audio. Không có 2 gói này thì
# lệnh diarize crash ImportError. Cài kèm để tính năng chạy được ngay.
uv pip install --quiet "torch==2.12.1" "pyannote.audio>=3.1,<4"
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("mlx-community/whisper-large-v3-mlx")
print("  Model OK")
PY

# 2. Tải engine + MCP server vào ~/wz-bien-ban/engine (self-contained)
echo "[3/4] Tải engine..."
for f in wz.py render.py glossary.yaml; do
  curl -fsSL "$RAW/plugins/workzone-meeting-note/scripts/$f" -o "$DATA/engine/$f"
done
curl -fsSL "$RAW/mcp/server.py" -o "$DATA/engine/server.py"
# Binary bắt tiếng hệ thống (ScreenCaptureKit) - thay BlackHole
curl -fsSL "https://github.com/workzone-vn/workzone-meeting-note/releases/download/v0.1.1/wz-syscap" -o "$DATA/engine/wz-syscap" || true
chmod +x "$DATA/engine/wz-syscap" 2>/dev/null || true
xattr -dr com.apple.quarantine "$DATA/engine/wz-syscap" 2>/dev/null || true

# 3. Claude Code plugin (nếu có claude CLI)
if command -v claude >/dev/null 2>&1; then
  echo "[4/4] Nạp plugin Claude Code..."
  claude plugin marketplace add workzone-vn/workzone-meeting-note 2>&1 | tail -1 || true
  claude plugin install workzone-meeting-note@work-zone 2>&1 | tail -1 || true
else
  echo "[4/4] (Bỏ qua plugin Claude Code - không thấy lệnh 'claude')"
fi

# 4. Đăng ký MCP cho Claude Desktop (nếu có Claude.app)
if [ -d "/Applications/Claude.app" ]; then
  python - <<PY
import json, pathlib, datetime
cfg = pathlib.Path.home()/"Library/Application Support/Claude/claude_desktop_config.json"
cfg.parent.mkdir(parents=True, exist_ok=True)
d = json.loads(cfg.read_text()) if cfg.exists() else {}
if cfg.exists():
    bak = cfg.with_suffix(".json.wzbak")
    bak.write_text(cfg.read_text())
d.setdefault("mcpServers", {})["workzone-meeting-note"] = {
    "command": str(pathlib.Path.home()/"wz-bien-ban/.venv/bin/python"),
    "args": [str(pathlib.Path.home()/"wz-bien-ban/engine/server.py")],
    "type": "stdio",
}
cfg.write_text(json.dumps(d, ensure_ascii=False, indent=2))
print("  Đã đăng ký MCP cho Claude Desktop (thoát/mở lại Claude Desktop để dùng).")
PY
fi

echo ""
echo "=================================================="
echo "  XONG. 2 cách dùng (tùy app bạn xài):"
echo "   • Claude Code:    gõ /bat-dau-hop  rồi  /ket-thuc-hop"
echo "   • Claude Desktop: nói 'bắt đầu họp' ... 'kết thúc họp, viết biên bản'"
echo "  Mở lại Claude để nạp. Lần ghi đầu, Mac hỏi quyền Micro -> Cho phép."
echo "=================================================="
