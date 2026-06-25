#!/usr/bin/env bash
# Cài BlackHole 2ch + bật chế độ "ghi tiếng trong máy".
# Cài driver cần mật khẩu admin (macOS bắt buộc cho driver âm thanh).
set -e
DATA="${WZ_DATA_DIR:-$HOME/wz-bien-ban}"
PKG_URL="https://existential.audio/downloads/BlackHole2ch-0.7.0.pkg"
PKG_SHA="a4a44ae3c2a89577b046886a5605f76dc78a3a08a627d59f22ead60f6434c37c"
DRIVER="/Library/Audio/Plug-Ins/HAL/BlackHole2ch.driver"

if [ -d "$DRIVER" ]; then
  echo "BlackHole đã có sẵn."
else
  echo "Tải BlackHole..."
  TMP="$DATA/BlackHole2ch.pkg"
  curl -fsSL "$PKG_URL" -o "$TMP"
  GOT=$(shasum -a 256 "$TMP" | awk '{print $1}')
  if [ "$GOT" != "$PKG_SHA" ]; then
    echo "Sai checksum, dừng cho an toàn."; rm -f "$TMP"; exit 1
  fi
  echo "Cài BlackHole (sẽ hỏi mật khẩu admin)..."
  # Cài + nạp lại CoreAudio trong cùng 1 phiên admin để BlackHole hiện ra ngay
  osascript -e "do shell script \"installer -pkg '$TMP' -target / && killall coreaudiod\" with administrator privileges"
  rm -f "$TMP"
  echo "Đã cài BlackHole + nạp lại âm thanh."
fi

# Bật chế độ ghi tiếng trong máy cho app
touch "$DATA/.system_audio"

# Mở Audio MIDI Setup để tạo Multi-Output (1 lần, để vừa nghe vừa thu)
open -a "Audio MIDI Setup" 2>/dev/null || true
echo "BẬT_THÀNH_CÔNG"
