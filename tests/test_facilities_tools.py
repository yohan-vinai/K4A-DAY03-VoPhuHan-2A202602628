"""Kiểm tra hành vi tools qua server mô phỏng, không gọi LLM."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from mcp_server import MCPFacilitiesServer


def interval(start='14:00', end='15:00'):
    return {key: f'2026-09-15T{value}:00+07:00'
            for key, value in [('start_time', start), ('end_time', end)]}


class FacilitiesTests(unittest.TestCase):
    def setUp(self):
        self.server = MCPFacilitiesServer()

    def call(self, tool, **args):
        response = self.server.call_tool(tool, args)
        self.assertEqual(response['jsonrpc'], '2.0')
        self.assertEqual(response['tool'], tool)
        self.assertEqual(response['server'], 'facilities-mcp-server')
        return response['result']

    def test_search_filters_and_does_not_book(self):
        result = self.call('find_available_rooms', **interval(), attendees=8, equipment=['máy chiếu', 'bảng trắng'])
        self.assertEqual([r['room_id'] for r in result['rooms']], ['A'])
        self.assertEqual(len(self.server.bookings), 1)
        self.assertEqual(self.call('find_available_rooms', **interval(), attendees=100, equipment=[])['rooms'], [])

    def test_book_and_requery(self):
        result = self.call('book_room', room_id='A', **interval('09:00', '10:00'))
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(self.server.bookings[-1]['booking_id'], result['booking_id'])
        self.assertEqual(self.call('book_room', room_id='A', **interval('09:00', '10:00'))['status'], 'CONFLICT')
        available = self.call('find_available_rooms', **interval('09:00', '10:00'), attendees=8, equipment=['máy chiếu'])
        self.assertNotIn('A', [r['room_id'] for r in available['rooms']])

    def test_search_then_book(self):
        room = self.call('find_available_rooms', **interval(), attendees=8, equipment=['máy chiếu'])['rooms'][0]
        self.assertEqual(self.call('book_room', room_id=room['room_id'], **interval())['status'], 'SUCCESS')

    def test_overlap_and_adjacent_boundaries(self):
        before = [b.copy() for b in self.server.bookings]
        for start, end in [('10:30', '11:30'), ('09:30', '10:30'), ('10:15', '10:45'), ('09:00', '12:00'), ('10:00', '11:00')]:
            with self.subTest(start=start, end=end):
                self.assertEqual(self.call('book_room', room_id='B', **interval(start, end))['status'], 'CONFLICT')
                self.assertEqual(self.server.bookings, before)
        for start, end in [('09:00', '10:00'), ('11:00', '12:00')]:
            self.assertEqual(self.call('book_room', room_id='B', **interval(start, end))['status'], 'SUCCESS')

    def test_invalid_inputs_leave_state_unchanged(self):
        cases = [
            ('book_room', {'room_id': 'A', **interval('15:00', '14:00')}),
            ('book_room', {'room_id': 'A', **interval('14:00', '14:00')}),
            ('book_room', {'room_id': 'A', 'start_time': '2026-09-15T14:00:00', 'end_time': '2026-09-15T15:00:00'}),
            ('book_room', {'room_id': 'A', **interval(), 'bookings': []}),
            ('book_room', {'room_id': 'A'}),
            ('find_available_rooms', {**interval(), 'attendees': 0, 'equipment': []}),
            ('find_available_rooms', {**interval(), 'attendees': True, 'equipment': []}),
            ('find_available_rooms', {**interval(), 'attendees': 8, 'equipment': 'máy chiếu'}),
        ]
        for tool, args in cases:
            with self.subTest(tool=tool, args=args):
                self.assertEqual(self.call(tool, **args)['status'], 'INVALID_ARGUMENTS')
        self.assertEqual(self.call('book_room', room_id='UNKNOWN', **interval())['status'], 'NOT_FOUND')
        self.assertEqual(self.call('unknown')['status'], 'UNKNOWN_TOOL')
        self.assertEqual(len(self.server.bookings), 1)

    def test_timezones_and_session_isolation(self):
        self.assertEqual(self.call('book_room', room_id='B', start_time='2026-09-15T03:30:00+00:00', end_time='2026-09-15T04:30:00+00:00')['status'], 'CONFLICT')
        self.call('book_room', room_id='A', **interval())
        self.assertEqual(len(MCPFacilitiesServer().bookings), 1)


if __name__ == '__main__':
    unittest.main()
