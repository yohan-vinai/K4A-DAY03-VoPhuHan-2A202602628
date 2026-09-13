"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI & Offline Mock)
Hỗ trợ Native Tool Calling và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.
"""

import os
import sys
import json
import time
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "", history=None) -> Dict[str, Any]:
        raise NotImplementedError

    def add_tool_results(self, history, results):
        raise NotImplementedError


class MockOfflineProvider(BaseLLMProvider):
    """Mô phỏng có quy tắc cho 5 test Facilities; không hiểu ngôn ngữ như LLM.

    Nhận ngày DD/MM/YYYY, giờ HH:MM và tên thiết bị tiếng Việt.
    Kết quả cuối lấy từ tools, không giả lập booking thành công.
    """
    model_name = "Facilities-Offline-Mock"

    def generate(self, prompt, system_prompt=""):
        return "[Mock Chatbot] Cần ngày, giờ bắt đầu/kết thúc, số người và thiết bị. Chatbot không có công cụ đặt phòng."

    def generate_with_tools(self, prompt, tools_schema, system_prompt="", history=None):
        history = history if history is not None else []
        text = prompt.casefold()
        wants_booking = "đặt" in text

        def answer(content):
            return {"type": "text", "content": "[Mock Facilities] " + content}

        def propose(name, arguments):
            return {"type": "tool_calls", "calls": [
                {"id": f"mock-{len(history)+1}", "name": name, "arguments": arguments}
            ]}

        if history:
            call, observation = history[-1]
            if observation.get("status") != "SUCCESS":
                return answer(observation.get("message") or observation.get("error", "Công cụ không xử lý thành công."))
            if call["name"] == "book_room":
                return answer(observation["message"] + " Mã booking: " + observation["booking_id"])
            rooms = observation.get("rooms", [])
            if not rooms:
                return answer("Không có phòng phù hợp. Bạn có thể đổi thời gian hoặc yêu cầu thiết bị/số người.")
            if wants_booking:
                args = call["arguments"]
                return propose("book_room", {"room_id": rooms[0]["room_id"],
                    "start_time": args["start_time"], "end_time": args["end_time"]})
            return answer("Phòng còn trống: " + "; ".join(
                f"{r['room_id']} ({r['capacity']} người; {', '.join(r['equipment'])})" for r in rooms))

        if "cung cấp" in text or "hướng dẫn" in text:
            return answer("Bạn cần cung cấp ngày, giờ bắt đầu/kết thúc và mã phòng cụ thể, hoặc số người và thiết bị để tìm phòng.")
        date = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
        times = re.findall(r"\b(\d{1,2}:\d{2})\b", text)
        if not date or len(times) != 2:
            return answer("Vui lòng cung cấp ngày DD/MM/YYYY và giờ bắt đầu/kết thúc HH:MM. Mock chưa hỗ trợ ngày tương đối như ngày mai.")
        try:
            values = [datetime.strptime(date[1] + " " + t, "%d/%m/%Y %H:%M").replace(
                tzinfo=timezone(timedelta(hours=7))).isoformat() for t in times]
        except ValueError:
            return answer("Ngày hoặc giờ không hợp lệ; vui lòng nhập lại.")
        args = dict(zip(("start_time", "end_time"), values))
        room = re.search(r"phòng\s+([a-z])\b", text)
        if wants_booking and room:
            return propose("book_room", {"room_id": room[1].upper(), **args})
        attendees = re.search(r"(\d+)\s*người", text)
        if not attendees:
            return answer("Bạn cần phòng cho bao nhiêu người và có yêu cầu thiết bị gì?")
        return propose("find_available_rooms", {**args, "attendees": int(attendees[1]),
            "equipment": [item for item in ("máy chiếu", "bảng trắng") if item in text]})

    def add_tool_results(self, history, results):
        history.extend(results)


class ProviderError(RuntimeError):
    """Lỗi API/cấu hình rõ ràng, không thay bằng kết quả Mock."""


def safe_error(exc, api_key):
    message = str(exc)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return f"{type(exc).__name__}: {message}"


def generate_gemini(client, **kwargs):
    """Thử lại tối đa 2 lần khi API cung cấp thời gian chờ quota ngắn."""
    for attempt in range(3):
        try:
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            details = getattr(exc, "details", None)
            delay = None
            if getattr(exc, "code", None) == 429 and isinstance(details, dict):
                for detail in details.get("error", details).get("details", []):
                    if detail.get("@type", "").endswith("RetryInfo"):
                        value = detail.get("retryDelay", "")
                        try:
                            delay = float(value.removesuffix("s")) + 1
                        except (ValueError, AttributeError):
                            pass
            if attempt == 2 or delay is None or not 0 < delay <= 60:
                raise
            print(f"⏳ API giới hạn tốc độ; chờ {delay:.0f}s rồi thử lại ({attempt+1}/2).", flush=True)
            time.sleep(delay)


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key=None, model=None):
        from google import genai
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            raise ProviderError("Chưa cấu hình GEMINI_API_KEY.")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        self.client = genai.Client(api_key=self.api_key, http_options={"timeout": 60000})

    def generate(self, prompt, system_prompt=""):
        return self.generate_with_tools(prompt, [], system_prompt)["content"]

    def generate_with_tools(self, prompt, tools_schema, system_prompt="", history=None):
        from google.genai import types
        history = history if history is not None else []
        if not history:
            history.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
        try:
            response = generate_gemini(self.client,
                model=self.model_name,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[types.Tool(function_declarations=tools_schema)] if tools_schema else None,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            if not response.candidates or not response.candidates[0].content:
                raise ProviderError("Gemini không trả về nội dung.")
            content = response.candidates[0].content
            # Preserve the complete model turn, including any thought signatures.
            history.append(content)
            calls = [part.function_call for part in content.parts or [] if part.function_call]
            if calls:
                return {"type": "tool_calls", "calls": [
                    {"id": call.id, "name": call.name, "arguments": dict(call.args or {})}
                    for call in calls
                ]}
            text = "".join(part.text for part in content.parts or [] if part.text and not part.thought)
            if not text.strip():
                raise ProviderError("Gemini không trả về câu trả lời hoặc tool call.")
            return {"type": "text", "content": text}
        except Exception as exc:
            raise ProviderError(safe_error(exc, self.api_key)) from None

    def add_tool_results(self, history, results):
        from google.genai import types
        history.append(types.Content(role="user", parts=[
            types.Part(function_response=types.FunctionResponse(
                id=call["id"], name=call["name"], response=observation,
            )) for call, observation in results
        ]))


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key=None, model=None):
        from openai import OpenAI
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            raise ProviderError("Chưa cấu hình OPENAI_API_KEY.")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        self.client = OpenAI(api_key=self.api_key, timeout=60, max_retries=0)

    def generate(self, prompt, system_prompt=""):
        return self.generate_with_tools(prompt, [], system_prompt)["content"]

    def generate_with_tools(self, prompt, tools_schema, system_prompt="", history=None):
        history = history if history is not None else []
        if not history:
            history.extend([{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}])
        try:
            kwargs = {"model": self.model_name, "messages": history}
            if tools_schema:
                kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools_schema]
            response = self.client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            history.append(msg.model_dump(exclude_none=True))
            if msg.tool_calls:
                return {"type": "tool_calls", "calls": [
                    {"id": call.id, "name": call.function.name, "arguments": json.loads(call.function.arguments)}
                    for call in msg.tool_calls
                ]}
            if not msg.content or not msg.content.strip():
                raise ProviderError("OpenAI không trả về câu trả lời hoặc tool call.")
            return {"type": "text", "content": msg.content}
        except Exception as exc:
            raise ProviderError(safe_error(exc, self.api_key)) from None

    def add_tool_results(self, history, results):
        history.extend({"role": "tool", "tool_call_id": call["id"],
                        "content": json.dumps(observation, ensure_ascii=False)}
                       for call, observation in results)


def get_llm_provider():
    provider_type = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider_type == "gemini":
        return GeminiProvider()
    if provider_type == "openai":
        return OpenAIProvider()
    if provider_type == "mock":
        return MockOfflineProvider()
    raise ProviderError(f"Provider không hỗ trợ: {provider_type}")
