"""
🚀 CORE AGENT APPLICATION (DAY 03: CHATBOT VS REACT AGENT)
Thực thi so sánh giữa Chatbot Baseline (Cấp 2) và ReAct Agent kết nối MCP Server (Cấp 3).
"""

import json
import os
import sys
import time
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from mcp_server import MCPFacilitiesServer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_AGENT_SYSTEM_PROMPT,
    MAX_ITERATIONS
)
from providers import get_llm_provider, ProviderError
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()

def load_test_cases():
    """Tải danh sách 5 test cases từ config/test_cases.json hoặc config/test_cases.example.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    if not os.path.exists(config_path):
        example_path = os.path.join(base_dir, "config", "test_cases.example.json")
        if os.path.exists(example_path):
            print("⚠️ [CONFIG NOTICE]: Chưa thấy file 'config/test_cases.json'. Đang dùng mẫu 'config/test_cases.example.json'.")
            print("👉 Hãy chạy: copy config/test_cases.example.json config/test_cases.json và viết test cases theo đề tài của bạn!\n")
            config_path = example_path
        else:
            config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_waterfall_trace(trace_data: list):
    """Ghi vết log Waterfall Trace Log ra file docs/trace_waterfall.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    trace_path = os.path.join(docs_dir, "trace_waterfall.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)
    print(f"📊 [OBSERVABILITY]: Đã lưu {len(trace_data)} sự kiện Waterfall Trace tại '{trace_path}'!")


def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không có công cụ gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot phản hồi:\n{response}")


def run_react_agent(user_query: str, provider, mcp_server: MCPFacilitiesServer, history=None) -> list:
    """Gửi Observation về LLM cho tới câu trả lời cuối hoặc giới hạn vòng lặp."""
    print(f"\n🤖 [REACT AGENT] {user_query}")
    history = history if history is not None else []
    trace_logs = []
    system_prompt = REACT_AGENT_SYSTEM_PROMPT + "\nThời gian hiện tại: " + datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
    metadata = {"query": user_query, "provider": type(provider).__name__, "model": provider.model_name,
                "timestamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()}
    for step in range(1, MAX_ITERATIONS + 1):
        start = time.perf_counter()
        try:
            response = provider.generate_with_tools(user_query, mcp_server.list_tools(), system_prompt, history=history)
        except ProviderError as exc:
            trace_logs.append({**metadata, "step": step, "action_type": "API_ERROR", "error": str(exc),
                               "latency_ms": round((time.perf_counter()-start)*1000, 2)})
            print(f"❌ [API ERROR] {exc}")
            return trace_logs
        trace_logs.append({**metadata, "step": step, "action_type": "LLM_RESPONSE",
                           "decision": response["type"], "latency_ms": round((time.perf_counter()-start)*1000, 2)})
        if response["type"] == "text":
            trace_logs.append({**metadata, "step": step, "action_type": "FINAL_ANSWER", "output": response["content"]})
            print(f"🏁 [Final Answer] {response['content']}")
            return trace_logs
        results = []
        for call in response["calls"]:
            start = time.perf_counter()
            observation = mcp_server.call_tool(call["name"], call["arguments"])["result"]
            results.append((call, observation))
            trace_logs.append({**metadata, "step": step, "action_type": "TOOL_EXECUTION",
                               "tool_name": call["name"], "arguments": call["arguments"], "observation": observation,
                               "latency_ms": round((time.perf_counter()-start)*1000, 2)})
            print(f"🛠️ {call['name']} → {json.dumps(observation, ensure_ascii=False)}")
        provider.add_tool_results(history, results)
    trace_logs.append({**metadata, "step": MAX_ITERATIONS, "action_type": "MAX_ITERATIONS",
                       "error": "Đã đạt giới hạn vòng lặp; xem trace để biết tool nào đã thực thi."})
    print("⚠️ Đạt giới hạn vòng lặp, chưa có câu trả lời cuối.")
    return trace_logs


if __name__ == "__main__":
    print("==========================================================")
    print("🏫 VINUNI AI COURSE - DAY 03 LAB: CHATBOT VS REACT AGENT")
    print("==========================================================")
    
    try:
        provider = get_llm_provider()
    except ProviderError as exc:
        print(f"❌ {exc}")
        sys.exit(1)
    mcp_server = MCPFacilitiesServer()
    
    print(f"🔌 LLM Provider: {provider.__class__.__name__} | Model: {provider.model_name}")
    print(f"🌐 MCP Server: {mcp_server.server_name}\n")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")
    
    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Trò chuyện trực tiếp với ReAct Agent:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Câu hỏi chung: 'Để đặt phòng họp, tôi cần cung cấp thông tin gì?'")
        print("   - Tra cứu: 'Tìm phòng cho 8 người có máy chiếu từ 14h đến 15h ngày 15/09/2026'")
        print("   - Đặt phòng: 'Đặt phòng A từ 9h đến 10h ngày 15/09/2026'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")
        while True:
            try:
                user_input = input("👤 Bạn hỏi: ").strip()
                if not user_input or user_input.lower() in ["exit", "quit"]:
                    print("👋 Tạm biệt! Kết thúc phiên trò chuyện.")
                    break
                logs = run_react_agent(user_input, provider, mcp_server)
                save_waterfall_trace(logs)
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát phiên tương tác.")
                break
    elif "--all" in sys.argv:
        print("🚀 [TEST SUITE MODE] Kiểm tra 5 Test Cases:")
        completed_count = 0
        error_count = 0
        todo_count = 0
        all_traces = []
        
        for tc in tests:
            print(f"\n==================================================")
            print(f"🧪 [{tc['id']}] Loại test: {tc['type']} (Độ phức tạp: {tc['complexity']})")
            print(f"📌 Kỳ vọng: {tc['expected_behavior']}")
            
            if tc["question"].strip().startswith("TODO"):
                print(f"⏸️ [CHƯA KÍCH HOẠT - ĐANG LÀ TODO]:")
                print(f"   {tc['question']}")
                print(f"   👉 Hãy mở file 'config/test_cases.json' để viết câu hỏi thực tế cho Test Case này!")
                todo_count += 1
            else:
                logs = run_react_agent(tc["question"], provider, MCPFacilitiesServer())
                for event in logs:
                    event["test_case_id"] = tc["id"]
                if not logs or logs[-1]["action_type"] != "FINAL_ANSWER":
                    error_count += 1
                all_traces.extend(logs)
                completed_count += 1
                
        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: Đã thực thi {completed_count}/{len(tests)} Test Cases | {todo_count} Test Cases đang chờ điền câu hỏi (TODO)")
        if all_traces:
            save_waterfall_trace(all_traces)
        print(f"Lượt lỗi/chạm giới hạn: {error_count}. Số đã chạy không phải số PASS; đối chiếu trace với kỳ vọng.")
        if error_count:
            sys.exit(1)
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")
    else:
        # Chế độ mặc định khi chỉ gõ 'python src/app.py'
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:   python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:    python src/app.py --all\n")
        
        sample_query = tests[1]["question"]
        print(f"--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU (TC02: Tra cứu phòng) ---")
        logs = run_react_agent(sample_query, provider, mcp_server)
        save_waterfall_trace(logs)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
