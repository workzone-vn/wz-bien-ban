#!/usr/bin/env bash
# Dựng môi trường WZ Biên Bản (gọi bởi /cai-dat). KHÔNG cần cài gì ngoài.
set -e
DATA="${WZ_DATA_DIR:-$HOME/wz-bien-ban}"
mkdir -p "$DATA/output"

# uv (trình quản lý môi trường Python) - tự cài nếu chưa có
if ! command -v uv >/dev/null 2>&1; then
  echo "[1/3] Cài uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "[1/3] uv OK"
fi

echo "[2/3] Tạo môi trường + thư viện (gồm ffmpeg đóng gói)..."
uv venv --python 3.12 "$DATA/.venv" >/dev/null 2>&1 || true
source "$DATA/.venv/bin/activate"
uv pip install --quiet mlx-whisper soundfile imageio-ffmpeg

echo "[3/3] Tải model Whisper large-v3 (~3GB, chỉ lần đầu)..."
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("mlx-community/whisper-large-v3-mlx")
print("Model OK")
PY

echo ""
echo "XONG. Dùng:  /bat-dau-hop   rồi   /ket-thuc-hop"
echo "(ffmpeg đã đóng gói sẵn - không cần cài ngoài. Chrome chỉ cần nếu muốn tự xuất PDF.)"
