#!/usr/bin/env bash
# Cài đặt WZ Biên Bản (1 lần). Tạo môi trường + tải model Whisper.
set -e
DATA="${WZ_DATA_DIR:-$HOME/wz-bien-ban}"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

echo "=== Cài đặt WZ Biên Bản ==="
mkdir -p "$DATA/output"

# 1. ffmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Chưa có ffmpeg. Cài bằng: brew install ffmpeg  (hoặc tải tại ffmpeg.org)"
  echo "Cài xong chạy lại lệnh này."
  exit 1
fi
echo "[1/4] ffmpeg OK"

# 2. uv (trình quản lý môi trường Python)
if ! command -v uv >/dev/null 2>&1; then
  echo "[2/4] Cài uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "[2/4] uv OK"
fi

# 3. venv + thư viện
echo "[3/4] Tạo môi trường + cài thư viện (mlx-whisper)..."
uv venv --python 3.12 "$DATA/.venv" >/dev/null 2>&1 || true
source "$DATA/.venv/bin/activate"
uv pip install --quiet mlx-whisper soundfile

# 4. Tải sẵn model large-v3 (~3GB) để lần đầu chạy không phải chờ
echo "[4/4] Tải model Whisper large-v3 (~3GB, chỉ lần đầu)..."
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("mlx-community/whisper-large-v3-mlx")
print("Model OK")
PY

echo ""
echo "=== XONG. Dùng trong Claude Code: ==="
echo "   gõ:  bắt đầu họp      -> ghi âm"
echo "   gõ:  kết thúc họp     -> ra biên bản + PDF"
echo ""
echo "Lưu ý lần đầu: macOS sẽ hỏi quyền Micro cho terminal -> bấm OK."
