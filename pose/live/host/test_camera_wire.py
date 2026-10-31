"""Hardware-free checks for portable board selection."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import camera_wire as wire


def board(device, serial_number, vid=0x1A86, pid=0x55D3):
    return SimpleNamespace(device=device, serial_number=serial_number, vid=vid, pid=pid)


class BoardSelectionTests(unittest.TestCase):
    def select(self, ports, serial_number=''):
        with patch.dict(os.environ, {'LJWB03_SERIAL': serial_number}), \
             patch.object(wire.list_ports, 'comports', return_value=ports), \
             patch.object(wire.serial, 'Serial') as connection:
            result = wire.select_port()
            connection.assert_not_called()
            return result

    def test_unique_matching_board(self):
        self.assertEqual(self.select([board('COM8', 'test-one'), board('COM9', 'other', vid=0)]), 'COM8')

    def test_multiple_boards_need_selection(self):
        with self.assertRaises(RuntimeError):
            self.select([board('COM8', 'test-one'), board('COM9', 'test-two')])

    def test_explicit_serial_selects_one(self):
        self.assertEqual(self.select([board('COM8', 'test-one'), board('COM9', 'test-two')], 'test-two'), 'COM9')

    def test_missing_or_wrong_board_rejected(self):
        for ports, number in (([], ''), ([board('COM8', 'test-one')], 'missing'),
                              ([board('COM8', 'test-one', pid=0)], '')):
            with self.subTest(ports=ports, number=number), self.assertRaises(RuntimeError):
                self.select(ports, number)


if __name__ == '__main__':
    unittest.main()
