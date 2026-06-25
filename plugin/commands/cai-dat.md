---
description: Cài đặt WZ Biên Bản (chạy 1 lần sau khi tải về)
---

Người dùng muốn CÀI ĐẶT WZ Biên Bản lần đầu. Chạy trình cài đặt bằng Bash tool:

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/install.sh"
```

Quá trình này: kiểm tra ffmpeg, cài uv, tạo môi trường Python, tải model Whisper large-v3 (~3GB, vài phút). Đây là chạy nền nặng nên nên dùng Bash tool với timeout lớn (tối đa 600000ms) hoặc chạy nền.

Sau khi xong:
- Nếu báo thiếu `ffmpeg`: hướng dẫn người dùng cài `brew install ffmpeg` rồi chạy lại.
- Báo người dùng: cài xong rồi, từ giờ chỉ cần **bắt đầu họp** và **kết thúc họp**.
- Nhắc: lần ghi âm đầu tiên macOS sẽ hỏi quyền Micro, bấm cho phép.

Lưu ý: tính năng tách người nói (ai nói câu nào) mặc định TẮT để cài là dùng được ngay. Nếu người dùng muốn bật, cần token HuggingFace miễn phí (hướng dẫn riêng).
