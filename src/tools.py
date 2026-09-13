"""
🛠️ TOOL DEFINITIONS & EXECUTION BACKEND
Mã nguồn chứa danh sách Tool Schemas (JSON Schema) và Execution Layer phục vụ cho MCP Server.
"""

import json
from datetime import datetime
from uuid import uuid4
from typing import Dict, Any

# ==============================================================================
# 1. KHAI BÁO TOOL SCHEMAS CHUẨN NATIVE JSON SCHEMA (TASK 1.2)
# ==============================================================================

TOOLS_SCHEMA = [
    {
        "name": "find_available_rooms",
        "description": (
            "Tra cứu các phòng họp còn trống trong toàn bộ khung giờ yêu cầu, "
            "đủ sức chứa và có tất cả thiết bị cần dùng. Chỉ tra cứu, không tạo booking."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Giờ bắt đầu theo ISO 8601, kèm múi giờ Việt Nam, ví dụ: 2026-09-15T14:00:00+07:00."
                },
                "end_time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Giờ kết thúc theo ISO 8601, kèm múi giờ Việt Nam; phải sau start_time, ví dụ: 2026-09-15T15:00:00+07:00."
                },
                "attendees": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Số người tham dự cuộc họp; phòng phải có sức chứa ít nhất bằng số này."
                },
                "equipment": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Danh sách thiết bị bắt buộc, ví dụ: ['máy chiếu', 'bảng trắng']. Dùng [] nếu không yêu cầu thiết bị."
                }
            },
            "required": ["start_time", "end_time", "attendees", "equipment"]
        }
    },
    {
        "name": "book_room",
        "description": (
            "Tạo booking cho một phòng họp cụ thể khi người dùng yêu cầu đặt phòng. "
            "Kiểm tra lại lịch trống và từ chối nếu trùng lịch, kể cả giao nhau một phần. "
            "Chỉ xác nhận đã đặt khi công cụ trả về thành công."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "room_id": {
                    "type": "string",
                    "description": "Mã phòng do người dùng chỉ định hoặc lấy từ kết quả find_available_rooms, ví dụ: A hoặc B. Không tự bịa mã phòng."
                },
                "start_time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Giờ bắt đầu theo ISO 8601, kèm múi giờ Việt Nam, ví dụ: 2026-09-15T09:00:00+07:00."
                },
                "end_time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Giờ kết thúc theo ISO 8601, kèm múi giờ Việt Nam; phải sau start_time, ví dụ: 2026-09-15T10:00:00+07:00."
                }
            },
            "required": ["room_id", "start_time", "end_time"]
        }
    }
]

# ==============================================================================
# 2. MÔ PHỎNG DỮ LIỆU & HÀM THỰC THI TOOL (EXECUTION LAYER)
# ==============================================================================

ROOMS = [
    {"room_id": "A", "capacity": 8, "equipment": ["máy chiếu", "bảng trắng"]},
    {"room_id": "B", "capacity": 12, "equipment": ["máy chiếu"]},
    {"room_id": "C", "capacity": 4, "equipment": ["bảng trắng"]},
]


def initial_bookings():
    """Dữ liệu mới cho mỗi phiên server; phục vụ tình huống trùng lịch TC05."""
    return [{
        "booking_id": "BK-SEED-001",
        "room_id": "B",
        "start_time": "2026-09-15T10:00:00+07:00",
        "end_time": "2026-09-15T11:00:00+07:00",
    }]


def parse_interval(start_time, end_time):
    """Kiểm tra thời gian trước khi đọc hoặc thay đổi booking."""
    if not isinstance(start_time, str) or not isinstance(end_time, str):
        raise ValueError("Thời gian phải là chuỗi ISO 8601 có múi giờ.")
    start = datetime.fromisoformat(start_time)
    end = datetime.fromisoformat(end_time)
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Thời gian phải có múi giờ, ví dụ +07:00.")
    if end <= start:
        raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
    return start, end


def has_conflict(room_id, start, end, bookings):
    # Khoảng [start, end): hai cuộc họp nối tiếp nhau được phép.
    return any(
        b["room_id"] == room_id
        and start < datetime.fromisoformat(b["end_time"])
        and end > datetime.fromisoformat(b["start_time"])
        for b in bookings
    )


def execute_find_available_rooms(start_time, end_time, attendees, equipment, *, bookings):
    start, end = parse_interval(start_time, end_time)
    if type(attendees) is not int or attendees < 1:
        raise ValueError("Số người phải là số nguyên dương.")
    if not isinstance(equipment, list) or any(
        not isinstance(item, str) or not item.strip() for item in equipment
    ):
        raise ValueError("Thiết bị phải là danh sách tên thiết bị; dùng [] nếu không yêu cầu.")
    required = {item.strip().casefold() for item in equipment}
    available = [
        room for room in ROOMS
        if room["capacity"] >= attendees
        and required.issubset({item.casefold() for item in room["equipment"]})
        and not has_conflict(room["room_id"], start, end, bookings)
    ]
    return json.dumps({"status": "SUCCESS", "rooms": available}, ensure_ascii=False)


def execute_book_room(room_id, start_time, end_time, *, bookings):
    start, end = parse_interval(start_time, end_time)
    if not isinstance(room_id, str) or not room_id.strip():
        raise ValueError("Mã phòng phải là chuỗi không rỗng.")
    room_id = room_id.strip().upper()
    if not any(room["room_id"] == room_id for room in ROOMS):
        return json.dumps({"status": "NOT_FOUND", "message": f"Không tìm thấy phòng {room_id}."}, ensure_ascii=False)
    if has_conflict(room_id, start, end, bookings):
        return json.dumps({"status": "CONFLICT", "message": f"Phòng {room_id} đã có booking trùng khung giờ yêu cầu."}, ensure_ascii=False)
    booking = {
        "booking_id": f"BK-{uuid4().hex[:12]}",
        "room_id": room_id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    }
    bookings.append(booking)
    return json.dumps({
        "status": "SUCCESS",
        **booking,
        "message": f"Đặt phòng {room_id} thành công từ {start_time} đến {end_time}.",
    }, ensure_ascii=False)


TOOL_ROUTER = {
    "find_available_rooms": execute_find_available_rooms,
    "book_room": execute_book_room,
}


def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any], *, bookings: list) -> str:
    """Chuyển yêu cầu tới tool; đầu vào lỗi không được tạo booking."""
    if tool_name not in TOOL_ROUTER:
        return json.dumps({"status": "UNKNOWN_TOOL", "error": f"Tool '{tool_name}' không tồn tại!"}, ensure_ascii=False)
    try:
        if not isinstance(arguments, dict):
            raise ValueError("Arguments phải là object.")
        schema = next(tool for tool in TOOLS_SCHEMA if tool["name"] == tool_name)["parameters"]
        if set(arguments) != set(schema["required"]):
            raise ValueError(f"Tham số cần có: {', '.join(schema['required'])}.")
        return TOOL_ROUTER[tool_name](**arguments, bookings=bookings)
    except (TypeError, ValueError) as exc:
        return json.dumps({"status": "INVALID_ARGUMENTS", "error": str(exc)}, ensure_ascii=False)
