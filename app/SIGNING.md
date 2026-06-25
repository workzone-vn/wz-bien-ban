# Ký + Notarize WZ Biên Bản.app

App build ra (`app/dist/WZ Bien Ban.app`) **chạy tốt trên máy đã build**, nhưng khi gửi cho người khác, macOS Gatekeeper sẽ chặn nếu app chưa được ký + notarize.

## Tạm thời (chưa ký) - người nhận tự mở
Người nhận: chuột phải vào app > **Open** > **Open** (qua được Gatekeeper 1 lần). Hoặc:
```
xattr -dr com.apple.quarantine "WZ Bien Ban.app"
```
Dùng nội bộ thì cách này đủ.

## Chính thức (gửi rộng) - cần Apple Developer ID (99$/năm)
Cần: tài khoản Apple Developer + chứng chỉ "Developer ID Application".

```bash
APP="app/dist/WZ Bien Ban.app"
CERT="Developer ID Application: Cong Ty CP Work Zone (TEAMID)"

# 1. Ký (hardened runtime + entitlements)
codesign --deep --force --options runtime \
  --entitlements app/entitlements.plist \
  --sign "$CERT" "$APP"

# 2. Đóng gói + notarize (cần app-specific password lưu trong keychain profile 'wz')
ditto -c -k --keepParent "$APP" WZ-Bien-Ban.zip
xcrun notarytool submit WZ-Bien-Ban.zip --keychain-profile wz --wait

# 3. Staple
xcrun stapler staple "$APP"
```

Sau khi notarize + staple, gửi `.app` (nén .zip hoặc .dmg) cho ai cũng mở được, không cảnh báo.

## Ghi chú
- Engine nặng (mlx-whisper, model 3GB) KHÔNG nằm trong .app - app gọi qua `~/wz-bien-ban/.venv`. Lần đầu mở app, nếu chưa có venv, app sẽ báo chạy lệnh cài (`curl ... install.sh | bash`).
- Quyền Micro: Info.plist đã khai `NSMicrophoneUsageDescription`; lần ghi đầu macOS hỏi cấp cho app.
