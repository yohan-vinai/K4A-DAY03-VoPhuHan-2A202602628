# BÁO CÁO BÀI LAB 3 — FACILITIES AGENT

- **Họ và tên:** Võ Phú Hãn
- **Mã học viên:** 2A202602628
- **Đề tài:** Trợ lý Đặt Phòng họp & Thiết bị (Facilities Agent)

## 1. AGENTIC FIT

| Tiêu chí | Điểm | Giải thích |
| :--- | :---: | :--- |
| Multi-step Reasoning | 4/5 | Tra cứu phòng, chọn phòng phù hợp rồi tạo booking; chuỗi xử lý ngắn. |
| Tool Interaction | 3/5 | Hai tools tra cứu và đặt phòng trên cùng nguồn dữ liệu mô phỏng; tích hợp đơn giản. |
| Dynamic Decision | 4/5 | Quyết định đặt phòng dựa trên kết quả tra cứu; báo thất bại khi trùng lịch. |
| Long Horizon Goal | 2/5 | Giữ điều kiện đặt phòng qua các bước trong một yêu cầu; chưa cần mục tiêu dài hạn. |
| **Tổng** | **13/20** | Phù hợp theo ngưỡng >12/20 của bài lab. |

**Phạm vi:** Phòng, thiết bị và booking là dữ liệu mô phỏng. MCP là lớp mô phỏng trong cùng chương trình; thiết bị đi kèm phòng.

## 2. TRACE NGHIỆM THU

Chạy ngày **13/09/2026**, dùng **Gemini API thật — `gemini-3.1-flash-lite`**, không fallback sang Mock. Mỗi test khởi tạo dữ liệu phòng riêng.

```bash
LLM_PROVIDER=gemini LLM_MODEL=gemini-3.1-flash-lite python src/app.py --all
```

TC04: `find_available_rooms → book_room → FINAL_ANSWER`. Trích rút gọn từ [trace_waterfall.json](trace_waterfall.json):

```json
{
  "test_case_id": "TC04",
  "step": 2,
  "action_type": "TOOL_EXECUTION",
  "tool_name": "book_room",
  "arguments": {
    "room_id": "A",
    "start_time": "2026-09-15T14:00:00+07:00",
    "end_time": "2026-09-15T15:00:00+07:00"
  },
  "observation": {
    "status": "SUCCESS",
    "booking_id": "BK-07769ec79a0e",
    "room_id": "A"
  },
  "latency_ms": 0.13
}
```

Trace đầy đủ có **20 sự kiện**. Thời gian gọi LLM và thực thi tool được đo riêng; log ghi quyết định gọi tool và kết quả, không phải suy luận nội bộ của mô hình.

## 3. KẾT QUẢ & NỘP BÀI

| Test | Kết quả đối chiếu trace | Đánh giá |
| :--- | :--- | :---: |
| TC01 | Hướng dẫn thông tin cần cung cấp, không gọi tool. | Đạt |
| TC02 | Tìm được phòng A/B đáp ứng điều kiện, không đặt phòng. | Đạt |
| TC03 | Đặt phòng A 09:00–10:00; trả đúng mã booking. | Đạt |
| TC04 | Tra cứu rồi đặt phòng A 14:00–15:00; trả đúng mã booking. | Đạt |
| TC05 | Phòng B trùng lịch; tool trả CONFLICT, Agent báo không đặt được. | Đạt |

- [x] Chạy đủ **5/5 test đạt** bằng LLM thật, đã đối chiếu tham số, kết quả tools và câu trả lời.
- **Số lượt gọi tool:** 5 (2 tra cứu, 3 đặt phòng; gồm 1 lần bị từ chối đúng do trùng lịch).
- [ ] Commit và push repo.
- [ ] Nộp link repo lên VLearn.
