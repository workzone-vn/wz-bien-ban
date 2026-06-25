---
description: Bắt đầu ghi âm cuộc họp (để tạo biên bản)
argument-hint: [tên cuộc họp]
---

Người dùng muốn BẮT ĐẦU ghi âm một cuộc họp.

Dùng Bash tool chạy lệnh sau (tên cuộc họp lấy từ `$ARGUMENTS`, để trống cũng được):

```
"$HOME/wz-bien-ban/.venv/bin/python" "${CLAUDE_PLUGIN_ROOT}/scripts/wz.py" record-start "$ARGUMENTS"
```

Sau khi chạy xong:
- Báo người dùng đang ghi âm.
- Nhắc ngắn gọn: nếu chưa cài BlackHole thì bật loa ngoài (không đeo tai nghe) để mic bắt được tiếng mọi người.
- Nói rõ: họp xong chỉ cần gõ **kết thúc họp** là có biên bản.

KHÔNG làm gì thêm. Không transcribe gì lúc này.
