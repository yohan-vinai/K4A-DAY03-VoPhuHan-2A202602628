"""Kiểm tra vòng lặp bằng phản hồi cố định; không thay Mock LLM của ứng dụng."""
import contextlib
import io
import sys
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app import run_react_agent, load_test_cases
from mcp_server import MCPFacilitiesServer
from providers import GeminiProvider, OpenAIProvider, MockOfflineProvider, ProviderError, generate_gemini
from google.genai.errors import ClientError
from google.genai import types


class ScriptedProvider:
    model_name = 'test-only'

    def __init__(self, responses):
        self.responses = iter(responses)
        self.observations = []

    def generate_with_tools(self, prompt, tools, system_prompt, history):
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

    def add_tool_results(self, history, results):
        self.observations.extend(results)
        history.extend(results)


def call(name, **args):
    return {'id': 'test-call', 'name': name, 'arguments': args}


class AgentTests(unittest.TestCase):
    def run_agent(self, provider):
        with contextlib.redirect_stdout(io.StringIO()):
            return run_react_agent('Tìm và đặt phòng', provider, MCPFacilitiesServer())

    def test_five_mock_cases_match_expected_actions_and_state(self):
        expected = {
            'TC01': [], 'TC02': ['find_available_rooms'], 'TC03': ['book_room'],
            'TC04': ['find_available_rooms', 'book_room'], 'TC05': ['book_room'],
        }
        with patch('google.genai.Client', side_effect=AssertionError('Mock must not call Gemini')):
            for case in load_test_cases():
                with self.subTest(case=case['id']), contextlib.redirect_stdout(io.StringIO()):
                    server = MCPFacilitiesServer()
                    logs = run_react_agent(case['question'], MockOfflineProvider(), server)
                    actions = [e for e in logs if e['action_type'] == 'TOOL_EXECUTION']
                    self.assertEqual([e['tool_name'] for e in actions], expected[case['id']])
                    self.assertEqual(logs[-1]['action_type'], 'FINAL_ANSWER')
                    self.assertTrue(all(e['provider'] == 'MockOfflineProvider' for e in logs))
                    if case['id'] in ('TC03', 'TC04'):
                        self.assertEqual(len(server.bookings), 2)
                        self.assertIn(server.bookings[-1]['booking_id'], logs[-1]['output'])
                    else:
                        self.assertEqual(len(server.bookings), 1)
                    if case['id'] == 'TC04':
                        self.assertIn(actions[1]['arguments']['room_id'], [r['room_id'] for r in actions[0]['observation']['rooms']])
                    if case['id'] == 'TC05':
                        self.assertEqual(actions[0]['observation']['status'], 'CONFLICT')

    def test_search_observation_drives_booking_then_final(self):
        times = {'start_time': '2026-09-15T14:00:00+07:00', 'end_time': '2026-09-15T15:00:00+07:00'}
        class DependentProvider(ScriptedProvider):
            def generate_with_tools(inner, prompt, tools, system_prompt, history):
                if not history:
                    return {'type': 'tool_calls', 'calls': [call('find_available_rooms', **times, attendees=8, equipment=['máy chiếu'])]}
                if len(history) == 1:
                    room_id = history[0][1]['rooms'][0]['room_id']
                    return {'type': 'tool_calls', 'calls': [call('book_room', **times, room_id=room_id)]}
                return {'type': 'text', 'content': history[1][1]['booking_id']}
        p = DependentProvider([])
        logs = self.run_agent(p)
        actions = [e for e in logs if e['action_type'] == 'TOOL_EXECUTION']
        self.assertEqual([e['tool_name'] for e in actions], ['find_available_rooms', 'book_room'])
        self.assertEqual(logs[-1]['output'], actions[-1]['observation']['booking_id'])

    def test_error_not_final_or_mock(self):
        logs = self.run_agent(ScriptedProvider([ProviderError('404 model unavailable')]))
        self.assertEqual(logs[-1]['action_type'], 'API_ERROR')
        self.assertFalse(any(e['action_type'] == 'FINAL_ANSWER' for e in logs))

    def test_iteration_limit_and_multiple_calls(self):
        responses = [{'type': 'tool_calls', 'calls': [call('unknown'), call('another_unknown')]}] * 5
        p = ScriptedProvider(responses)
        logs = self.run_agent(p)
        self.assertEqual(logs[-1]['action_type'], 'MAX_ITERATIONS')
        self.assertEqual(len(p.observations), 10)

    def test_openai_history_keeps_call_and_result_ids(self):
        from openai.types.chat import ChatCompletionMessage
        msg = ChatCompletionMessage(role="assistant", tool_calls=[{
            "id": "call-1", "type": "function",
            "function": {"name": "find_available_rooms", "arguments": "{}"}
        }])
        create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=msg)]))
        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider.api_key, provider.model_name = 'not-a-key', 'test'
        provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        history = []
        response = provider.generate_with_tools('question', [], history=history)
        provider.add_tool_results(history, [(response['calls'][0], {'status': 'SUCCESS'})])
        self.assertEqual(history[-2]['tool_calls'][0]['id'], 'call-1')
        self.assertEqual(history[-1]['tool_call_id'], 'call-1')
        self.assertEqual([m['role'] for m in history], ['system', 'user', 'assistant', 'tool'])

    def test_quota_retry_is_bounded_and_does_not_hide_other_errors(self):
        error = ClientError(429, {"error": {"code": 429, "message": "quota", "details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "2s"}
        ]}})
        generate = Mock(side_effect=[error, "success"])
        client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
        with patch('providers.time.sleep') as sleep:
            self.assertEqual(generate_gemini(client), 'success')
            sleep.assert_called_once_with(3)
        generate.side_effect = error
        generate.reset_mock()
        with patch('providers.time.sleep'), self.assertRaises(ClientError):
            generate_gemini(client)
        self.assertEqual(generate.call_count, 3)
        generate.side_effect = RuntimeError('network failure')
        with patch('providers.time.sleep') as sleep, self.assertRaises(RuntimeError):
            generate_gemini(client)
        sleep.assert_not_called()

    def test_gemini_preserves_native_turn_and_matches_tool_ids(self):
        signature = b'test-signature'
        content = types.Content(role='model', parts=[
            types.Part(function_call=types.FunctionCall(id='one', name='find_available_rooms', args={}), thought_signature=signature),
            types.Part(function_call=types.FunctionCall(id='two', name='find_available_rooms', args={})),
        ])
        seen = []
        def generate(**kwargs):
            seen.append(list(kwargs['contents']))
            return SimpleNamespace(candidates=[SimpleNamespace(content=content)])
        provider = GeminiProvider.__new__(GeminiProvider)
        provider.api_key, provider.model_name = 'not-a-key', 'test'
        provider.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
        history = []
        response = provider.generate_with_tools('question', [], history=history)
        self.assertIs(history[-1], content)
        self.assertEqual(history[-1].parts[0].thought_signature, signature)
        provider.add_tool_results(history, [(c, {'status': 'SUCCESS'}) for c in response['calls']])
        self.assertEqual([part.function_response.id for part in history[-1].parts], ['one', 'two'])
        provider.generate_with_tools('question', [], history=history)
        self.assertEqual(len(seen[1]), 3)


if __name__ == '__main__':
    unittest.main()
