import tempfile
import unittest
from pathlib import Path

import scene_test as st


def det(seq, people, host):
    return {'seq': seq, 't_ms': seq * 160, 'host_rx': host,
            'people': [{'score': s, 'center': c, 'box': [0, 0, 1, 1]} for s, c in people]}


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class Tests(unittest.TestCase):
    def test_false_alarm_rate_when_seat_is_empty(self):
        r = st.SceneRecorder()
        r.start('empty')
        for i in range(10):
            r.on_det(det(i, [(0.8, [10, 10])] if i < 2 else [], i))
        m = r.results()[0]
        self.assertEqual((m['frames'], m['false_alarm_pct']), (10, 20.0))

    def test_detection_rate_score_and_center_jitter(self):
        r = st.SceneRecorder()
        r.start('near')
        centers = [[160, 120], [162, 120], [158, 120], [160, 124]]
        for i, c in enumerate(centers):
            r.on_det(det(i, [(0.9, c)], i))
        r.on_det(det(9, [], 9))
        r.on_det(det(10, [(0.9, [160, 120]), (0.75, [20, 20])], 10))
        m = r.results()[0]
        self.assertEqual(m['detected_pct'], 83.3)
        self.assertEqual(m['multi_pct'], 16.7)
        self.assertEqual(m['score_min'], 0.9)
        self.assertEqual(m['center_std_px'][0], 1.3)
        self.assertEqual(m['center_p95_px'], 4.0)

    def test_leave_and_return_reaction_times(self):
        clock = Clock()
        r = st.SceneRecorder(clock)
        r.start('leave_return')
        r.on_det(det(1, [(0.9, [1, 1])], 100.0))
        clock.t = 101.0
        r.mark('leave')
        r.on_det(det(2, [(0.9, [1, 1])], 101.2))
        r.on_det(det(3, [], 101.9))
        clock.t = 105.0
        r.mark('return')
        r.on_det(det(4, [], 105.3))
        r.on_det(det(5, [(0.9, [1, 1])], 106.5))
        m = r.results()[0]
        self.assertEqual(m['reactions'], [{'event': 'leave', 'seconds': 0.9}, {'event': 'return', 'seconds': 1.5}])
        with self.assertRaises(ValueError):
            r.start('near'); r.mark('leave')

    def test_pose_results_are_tallied_and_saved(self):
        r = st.SceneRecorder()
        r.start('posture')
        r.on_pose(1, {'state': 'head_down', 'level': 'watch'}, True)
        r.on_pose(2, {'state': 'no_person', 'level': 'unknown'}, False)
        r.end()
        r.on_det(det(3, [], 3))
        m = r.results()[0]
        self.assertEqual((m['frames'], m['pose_frames'], m['pose_person_pct']), (0, 2, 50.0))
        self.assertEqual(m['pose_states'], {'head_down': 1, 'no_person': 1})
        with tempfile.TemporaryDirectory() as tmp:
            path = r.save(Path(tmp))
            self.assertIn('"posture"', path.read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            r.start('bogus')


if __name__ == '__main__':
    unittest.main()
