#!/usr/bin/env bash
# WZ Biên Bản - CÀI 1 PHÁT. Tự nạp plugin vào Claude Code + dựng môi trường.
# Khách chỉ cần chạy (hoặc bảo Claude Code chạy):
#   curl -fsSL https://raw.githubusercontent.com/workzone-vn/wz-bien-ban/main/install.sh | bash
set -e
DATA="${WZ_DATA_DIR:-$HOME/wz-bien-ban}"
mkdir -p "$DATA/output"

echo "=================================================="
echo "   Cài đặt WZ Biên Bản"
echo "=================================================="

# 1. Claude Code (bắt buộc - đây là nền tảng chạy plugin)
if ! command -v claude >/dev/null 2>&1; then
  echo "Chưa thấy Claude Code trên máy."
  echo "Cài Claude Code tại: https://claude.com/claude-code  (hoặc dùng app Claude Desktop có Claude Code)."
  echo "Cài xong chạy lại lệnh này."
  exit 1
fi
echo "[1/3] Claude Code OK"

# 2. Nạp plugin (không cần ffmpeg/brew/chrome cài tay)
echo "[2/3] Nạp plugin WZ Biên Bản..."
claude plugin marketplace add workzone-vn/wz-bien-ban 2>&1 | tail -1 || true
claude plugin install wz-bien-ban@work-zone 2>&1 | tail -1 || true

# 3. Môi trường + ffmpeg đóng gói + model
echo "[3/3] Dựng môi trường + tải model (ffmpeg đóng gói sẵn, không cần cài ngoài)..."
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  export PATH="$HOME/.local/bin:$PATH"
fi
uv venv --python 3.12 "$DATA/.venv" >/dev/null 2>&1 || true
source "$DATA/.venv/bin/activate"
uv pip install --quiet mlx-whisper soundfile imageio-ffmpeg "mcp[cli]"
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("mlx-community/whisper-large-v3-mlx")
print("Model OK")
PY

echo ""
echo "=================================================="
echo "  XONG. Hãy MỞ LẠI Claude Code, rồi dùng:"
echo "     /bat-dau-hop     (bắt đầu ghi họp)"
echo "     /ket-thuc-hop    (ra biên bản + PDF)"
echo ""
echo "  Không cần cài ffmpeg/Chrome riêng. Lần ghi đầu, Mac hỏi"
echo "  quyền Micro thì bấm Cho phép."
echo "=================================================="
