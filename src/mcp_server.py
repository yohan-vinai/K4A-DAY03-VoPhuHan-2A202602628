"""Server Facilities mô phỏng trong cùng tiến trình, theo giao diện của bài lab.

Envelope có nhãn jsonrpc để phục vụ bài tập; đây chưa phải MCP transport đầy đủ.
"""

import json
from typing import Dict, Any, List
from tools import TOOLS_SCHEMA, dispatch_tool_call, initial_bookings


class MCPFacilitiesServer:
    def __init__(self, server_name: str = "facilities-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"
        self.bookings = initial_bookings()

    def list_tools(self) -> List[Dict[str, Any]]:
        return TOOLS_SCHEMA

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Task 2.1: dispatch, giải mã JSON và đóng gói theo mẫu codelab."""
        content = json.loads(dispatch_tool_call(tool_name, arguments, bookings=self.bookings))
        return {
            "jsonrpc": "2.0",
            "server": self.server_name,
            "tool": tool_name,
            "result": content,
        }


# Giữ tương thích với import hiện tại trong app.py cho tới Task 2.2.
MCPAcademicServer = MCPFacilitiesServer


if __name__ == "__main__":
    server = MCPFacilitiesServer()
    tools = server.list_tools()
    assert {tool["name"] for tool in tools} == {"find_available_rooms", "book_room"}
    assert all(tool["parameters"]["properties"] and tool["parameters"]["required"] for tool in tools)
    print(f"✅ [MCP SERVER] Đã khởi tạo thành công {server.server_name} (Version: {server.version})")
    print(f"📦 Số lượng Tools công bố qua MCP: {len(tools)}")
    result = server.call_tool("find_available_rooms", {
        "start_time": "2026-09-15T14:00:00+07:00",
        "end_time": "2026-09-15T15:00:00+07:00",
        "attendees": 8,
        "equipment": ["máy chiếu"],
    })
    assert result["result"]["status"] == "SUCCESS" and result["result"]["rooms"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("✅ [CHECKPOINT 2] Công bố 2 tools và tra cứu qua server thành công.")
