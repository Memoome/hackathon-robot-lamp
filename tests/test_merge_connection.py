"""Regression coverage for merged connection behavior without hardware or UI."""
import ast
import pathlib
import queue
import re
import sys
import time
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]

class MergeConnectionTests(unittest.TestCase):
    def connect(self, active, moving, boot=False):
        tree = ast.parse((ROOT / 'apps/LJWB03-Lamp-Demo/lamp_demo.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LampLink')
        worker = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'worker')
        scope = dict(queue=queue, time=time, re=re, board_port=None, serial=None,
                     EMOTION=b'emotion_count=', Cancelled=type('Cancelled', (Exception,), {}))
        exec(compile(ast.Module(body=[worker], type_ignores=[]), '<worker>', 'exec'), scope)
        commands=[]; events=[]
        def exchange(command, *args):
            commands.append(command)
            return b'boot_rest=1 emotion_count=10' if boot else b'emotion_count=10'
        link = types.SimpleNamespace(s=None, session=None, jobs=queue.Queue(),
            state=dict(active=active,moving=moving,base_spin=0,session=42),
            exchange=exchange, emit=lambda *a:events.append(a), stop_hardware=lambda *a:None)
        link.jobs.put(('connect',None));link.jobs.put(('close',None))
        module=types.SimpleNamespace(open_connection=lambda *a:('fake',types.SimpleNamespace(close=lambda:None)))
        with patch.dict(sys.modules, {'wireless_link':module}):scope['worker'](link)
        self.assertTrue(any(e[0]=='connected' for e in events), events)
        self.assertFalse(any(c.startswith('arm_live engage') for c in commands))
        return commands

    def test_stationary_boot_pose_is_claimed(self):
        cmds=self.connect([1]*4,[0]*4,True)
        self.assertIn('arm_live claim',cmds);self.assertNotIn('arm_live freeze',cmds)

    def test_existing_movement_is_frozen_without_claim(self):
        cmds=self.connect([1]*4,[1,0,0,0],True)
        self.assertIn('arm_live freeze',cmds);self.assertNotIn('arm_live claim',cmds)

    def test_released_and_ordinary_held_connections_remain_read_only(self):
        for active in ([0]*4,[1]*4):
            cmds=self.connect(active,[0]*4)
            self.assertEqual(cmds,['arm_live status','audio_test status'])

if __name__=='__main__':unittest.main()
