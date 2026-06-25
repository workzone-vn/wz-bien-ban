#!/usr/bin/env bash
# WZ Biên Bản - cài đặt 1 phát. Tự nạp plugin vào Claude Code + dựng môi trường.
#   Khách chỉ chạy:  bash bootstrap.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=================================================="
echo "   Cài đặt WZ Biên Bản"
echo "=================================================="

if ! command -v claude >/dev/null 2>&1; then
  echo "Chưa thấy Claude Code. Cài tại https://claude.com/claude-code rồi chạy lại."
  exit 1
fi

echo "[1/3] Nạp plugin vào Claude Code..."
claude plugin marketplace add "$DIR" 2>&1 | tail -1 || true
claude plugin install wz-bien-ban@work-zone --scope user 2>&1 | tail -1 || true

echo "[2/3] Dựng môi trường + tải model (lần đầu ~vài phút)..."
bash "$DIR/scripts/install.sh"

echo "[3/3] Xong."
echo ""
echo "=================================================="
echo "  MỞ LẠI Claude Code, rồi dùng:"
echo "     /bat-dau-hop     (bắt đầu ghi họp)"
echo "     /ket-thuc-hop    (ra biên bản + PDF)"
echo "=================================================="
