import ast
import pathlib
import sys
import unittest
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/LJWB03-Lamp-Demo'))
from visual_interaction import SedentaryTrigger, HeadDownTrigger, VisualActionTrigger, PresenceLight, visible_person


def snapshot(seconds=10, updated=100):
    return dict(active=True, presence=dict(updated=updated, sit_s=seconds,
        present=True, stable=True, states=dict(away=False, standing=False,
        sedentary='alert' if seconds >= 10 else 'ok')))


class TriggerTests(unittest.TestCase):
    def test_threshold_once_and_rest_rearm(self):
        gate = SedentaryTrigger()
        self.assertFalse(gate.update(snapshot(9), True, 100))
        self.assertTrue(gate.update(snapshot(10, 101), True, 101))
        self.assertFalse(gate.update(snapshot(30, 102), True, 102))
        gate.update(snapshot(0, 103), True, 103)
        self.assertTrue(gate.update(snapshot(10, 104), True, 104))

    def test_no_stale_inactive_absent_standing_or_unstable_trigger(self):
        for key, value in [('present', False), ('stable', False)]:
            data = snapshot(); data['presence'][key] = value
            self.assertFalse(SedentaryTrigger().update(data, True, 100))
        for key in ['away', 'standing']:
            data = snapshot(); data['presence']['states'][key] = True
            self.assertFalse(SedentaryTrigger().update(data, True, 100))
        data = snapshot(); data['active'] = False
        self.assertFalse(SedentaryTrigger().update(data, True, 100))
        self.assertFalse(SedentaryTrigger().update(snapshot(), True, 104))
        self.assertFalse(SedentaryTrigger().update(snapshot(), True, 99))

    def test_busy_event_not_replayed(self):
        gate = SedentaryTrigger()
        self.assertFalse(gate.update(snapshot(), False, 100))
        self.assertFalse(gate.update(snapshot(updated=101), True, 101))

    def test_studio_uses_existing_water_and_ignores_old_toggle_response(self):
        # Execute the actual handler without a GUI or a hardware connection.
        source = ast.parse((ROOT / 'apps/LJWB03-Lamp-Demo/visual_control.py').read_text())
        cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'App')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'handle_visual_presence')
        import time
        ns = {'time': time, 'visible_person': visible_person}; exec(compile(ast.Module(body=[method], type_ignores=[]), '<handler>', 'exec'), ns)
        calls = []
        gate = VisualActionTrigger()
        import time
        app = SimpleNamespace(link=SimpleNamespace(), visual_generation=2, visual_fetching=True,
            visual_enabled=SimpleNamespace(get=lambda: True), visual_status=SimpleNamespace(set=lambda text: None),
            connected=True, busy=False, previewing=False, control_held=False, base_control_held=False,
            match_angles=None, range_edit=SimpleNamespace(get=lambda: False), state={'active':[1]*4},
            visual_trigger=gate, count=10, action_rows=lambda kind: calls.append(kind) or ['existing'],
            gesture_config=lambda rows: {'same_config': True}, send=lambda *args: calls.append(args))
        handler = ns['handle_visual_presence']
        handler(app, (1, snapshot(updated=time.time()), None))
        self.assertEqual(calls, [])
        handler(app, (2, snapshot(updated=time.time()), None))
        self.assertEqual(calls, ['Water', ('slump', (['existing'], {'same_config':True}, 10))])
        handler(app, (2, snapshot(updated=time.time()), None))
        self.assertEqual(len(calls), 2)

def pose_snapshot(t, level='watch', active=True):
    return dict(active=active, pc_pose=dict(updated=t, posture=dict(
        calibrated=True, calibrating=False, levels={'head_down': level})))


class HeadDownTests(unittest.TestCase):
    def test_five_seconds_once_then_normal_rearms(self):
        gate = HeadDownTrigger()
        for t in [100, 102, 104]:
            self.assertFalse(gate.update(pose_snapshot(t), True, t))
        self.assertTrue(gate.update(pose_snapshot(105), True, 105))
        self.assertFalse(gate.update(pose_snapshot(108), True, 108))
        gate.update(pose_snapshot(109, 'ok'), True, 109)
        for t in [110, 113]: gate.update(pose_snapshot(t), True, t)
        self.assertTrue(gate.update(pose_snapshot(115), True, 115))

    def test_cached_frames_unknown_gaps_and_busy_do_not_count(self):
        for interruption in ['unknown', 'inactive', 'busy', 'stale', 'gap']:
            gate = HeadDownTrigger()
            gate.update(pose_snapshot(100), True, 100)
            self.assertFalse(gate.update(pose_snapshot(100), True, 102))
            if interruption == 'unknown': gate.update(pose_snapshot(103, 'unknown'), True, 103)
            if interruption == 'inactive': gate.update(pose_snapshot(103, active=False), True, 103)
            if interruption == 'busy': gate.update(pose_snapshot(103), False, 103)
            if interruption == 'stale': gate.update(pose_snapshot(100), True, 104)
            self.assertFalse(gate.update(pose_snapshot(106), True, 106))

    def test_independent_mapping_and_simultaneous_priority(self):
        gate = VisualActionTrigger()
        for t in [100, 103]:
            self.assertIsNone(gate.update(pose_snapshot(t), True, t))
        data = snapshot(updated=105); data.update(pc_pose=pose_snapshot(105)['pc_pose'])
        self.assertEqual(gate.update(data, True, 105), 'Stretch')
        data['presence']['updated'] = 106
        self.assertIsNone(gate.update(data, True, 106))
        self.assertEqual(VisualActionTrigger().update(snapshot(), True, 100), 'Water')

class PresenceLightTests(unittest.TestCase):
    def test_off_immediate_on_breathe_and_reset(self):
        light = PresenceLight()
        self.assertEqual(light.rgb(False, 0), [0, 0, 0])
        first = light.rgb(True, 1)
        self.assertGreater(first[0], 0)
        peak = light.rgb(True, 3)
        self.assertGreater(peak[0], first[0])
        self.assertEqual(light.rgb(True, 5), first)
        self.assertEqual(light.rgb(False, 6), [0, 0, 0])
        self.assertEqual(light.rgb(True, 7), first)

    def test_actual_idle_writer_restores_action_light_and_expires(self):
        source = ast.parse((ROOT / 'apps/LJWB03-Lamp-Demo/visual_control.py').read_text())
        cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'VisualLink')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'idle')
        clock = [100.0]
        ns = {'time': SimpleNamespace(monotonic=lambda: clock[0]), 'PresenceLight': PresenceLight}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<idle>', 'exec'), ns)
        commands = []
        link = SimpleNamespace(presence_light_context=(True, True, 103),
            exchange=lambda command, pattern: commands.append(command) or b'LED_STATUS r=1 g=1 b=1',
            emit=lambda *args: None)
        ns['idle'](link)
        self.assertNotEqual(commands[-1], 'lamp_led set 0 0 0')
        count = len(commands)
        ns['idle'](link)
        self.assertEqual(len(commands), count)
        link.presence_light_dirty = True
        ns['idle'](link)
        self.assertEqual(len(commands), count+1)
        clock[0] = 104
        ns['idle'](link)
        self.assertEqual(commands[-1], 'lamp_led set 0 0 0')
        link.presence_light_context = (False, False, 0)
        ns['idle'](link)
        self.assertIsNone(link.presence_light_context)

    def test_first_person_needs_no_stability_or_sitting_threshold(self):
        data = snapshot(0)
        data['presence']['stable'] = False
        data['presence']['states']['away'] = True
        self.assertTrue(visible_person(data, 100))
        self.assertFalse(visible_person(data, 104))
        data['presence']['present'] = False
        self.assertFalse(visible_person(data, 100))
        data['presence']['present'] = True
        data['active'] = False
        self.assertFalse(visible_person(data, 100))

if __name__ == '__main__': unittest.main()
