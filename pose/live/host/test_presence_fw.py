"""Builds and runs the board presence state machine test on the host C compiler."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

FW = Path(__file__).resolve().parents[1] / 'firmware'


@unittest.skipUnless(shutil.which('cc'), 'needs a host C compiler')
class PresenceFirmwareTest(unittest.TestCase):
    def test_rules_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / 'test_presence'
            subprocess.run(['cc', '-std=c99', '-Wall', '-Werror', '-I', str(FW / 'main'), str(FW / 'test' / 'test_presence.c'),
                            str(FW / 'main' / 'presence.c'), '-lm', '-o', str(exe)], check=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        lines = [json.loads(line) for line in out.splitlines()]
        self.assertEqual(len(lines), 6)
        first, calibrated, close, standing, auto, two = lines
        self.assertEqual(first['states'], {'away': False, 'sedentary': 'ok', 'too_close': 'unknown', 'standing': False})
        self.assertIsNone(first['metrics']['area_ratio'])
        self.assertFalse(first['calibrated'])
        self.assertIsNone(first['calib_source'])
        self.assertEqual(calibrated['calib_source'], 'manual')
        self.assertEqual((auto['calib_source'], auto['calib_hint']), ('auto', None))
        self.assertTrue(calibrated['calibrated'])
        self.assertAlmostEqual(calibrated['metrics']['area_ratio'], 1.0, places=3)
        self.assertEqual(close['states']['too_close'], 'alert')
        self.assertGreaterEqual(close['metrics']['area_ratio'], 1.5)
        self.assertTrue(standing['states']['standing'])
        self.assertEqual(two['main'], [112, 62, 212, 242])


if __name__ == '__main__':
    unittest.main()
