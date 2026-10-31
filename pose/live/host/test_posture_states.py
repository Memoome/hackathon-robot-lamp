import unittest

import posture_states as ps

W, H = 320, 240


def person(nose=(160, 70), shoulders=((200, 120), (120, 120)), eyes=((172, 62), (148, 62)),
           ears=((185, 66), (135, 66)), wrists=(None, None)):
    pts = [None] * 17
    pts[ps.NOSE] = list(nose) if nose else None
    pts[ps.LEYE], pts[ps.REYE] = [list(e) if e else None for e in eyes]
    pts[ps.LEAR], pts[ps.REAR] = [list(e) if e else None for e in ears]
    pts[ps.LSH], pts[ps.RSH] = [list(s) for s in shoulders]
    pts[ps.LWR], pts[ps.RWR] = [list(w) if w else None for w in wrists]
    return {'score': 0.9, 'box': [100, 20, 220, 239], 'keypoints': pts}


def calibrated(c=None):
    c = c or ps.PostureClassifier()
    c.start_calibration()
    for i in range(3):
        r = c.update(person(), 1, W, H, i, i)
    assert r['calibrated'], r
    return c


class Tests(unittest.TestCase):
    def test_features_normalise_by_shoulder_width(self):
        f, reason = ps.features(person(), W, H)
        self.assertEqual(reason, '')
        self.assertAlmostEqual(f['head_drop'], (70 - 120) / 80)
        self.assertAlmostEqual(f['shoulder'], 0)
        self.assertAlmostEqual(f['head_tilt_deg'], 0)
        self.assertFalse(f['desk'])
        self.assertFalse(f['stretch'])

    def test_missing_shoulders_cannot_be_judged(self):
        p = person()
        p['keypoints'][ps.RSH] = None
        c = calibrated()
        r = c.update(p, 1, W, H, 10, 10)
        self.assertEqual((r['state'], r['level']), ('unknown', 'unknown'))

    def test_needs_calibration_and_rejects_unstable_baseline(self):
        c = ps.PostureClassifier()
        self.assertEqual(c.update(person(), 1, W, H, 0, 1)['state'], 'not_calibrated')
        c.start_calibration()
        c.update(person(), 1, W, H, 0, 1)
        r = c.update(person(nose=(160, 90)), 1, W, H, 1, 2)
        r = c.update(person(), 1, W, H, 2, 3)
        self.assertFalse(r['calibrated'])
        self.assertIn('变化过大', r['message'])

    def test_head_down_watch_then_alert_after_30s_and_3_samples(self):
        c = calibrated()
        down = person(nose=(160, 85))
        r = c.update(down, 1, W, H, 10, 10)
        self.assertEqual((r['state'], r['level']), ('head_down', 'watch'))
        r = c.update(down, 1, W, H, 25, 11)
        self.assertEqual(r['level'], 'watch')
        r = c.update(down, 1, W, H, 41, 12)
        self.assertEqual((r['state'], r['level'], r['duration_s']), ('head_down', 'alert', 31))
        r = c.update(person(), 1, W, H, 42, 13)
        self.assertEqual((r['state'], r['level']), ('normal', 'ok'))

    def test_head_tilt_and_shoulder_tilt(self):
        c = calibrated()
        r = c.update(person(eyes=((172, 70), (148, 56))), 1, W, H, 10, 10)
        self.assertEqual(r['levels']['head_tilt'], 'watch')
        r = c.update(person(shoulders=((200, 132), (120, 118))), 1, W, H, 11, 11)
        self.assertEqual(r['levels']['shoulder_tilt'], 'watch')

    def test_head_on_desk_wins_over_head_down(self):
        c = calibrated()
        desk = person(nose=(160, 118))
        r = c.update(desk, 1, W, H, 10, 10)
        self.assertEqual(r['state'], 'head_on_desk')
        self.assertEqual(r['levels']['head_down'], 'watch')
        face_hidden = person(nose=None, eyes=(None, None), ears=((185, 66), None))
        self.assertEqual(c.update(face_hidden, 1, W, H, 11, 11)['state'], 'head_on_desk')

    def test_stretch_is_an_event_with_cooldown(self):
        c = calibrated()
        up = person(wrists=((210, 20), (110, 20)))
        self.assertEqual(c.update(up, 1, W, H, 10, 10)['events'], ['stretch'])
        self.assertEqual(c.update(up, 1, W, H, 12, 11)['events'], [])
        self.assertEqual(c.update(up, 1, W, H, 21, 12)['events'], ['stretch'])

    def test_no_person_and_long_gap_clear_timers(self):
        c = calibrated()
        c.update(person(nose=(160, 85)), 1, W, H, 10, 10)
        self.assertEqual(c.update(None, 0, W, H, 11, 11)['state'], 'no_person')
        r = c.update(person(nose=(160, 85)), 1, W, H, 12, 12)
        self.assertEqual(r['duration_s'], 0)
        c.update(person(nose=(160, 85)), 1, W, H, 13, 13)
        r = c.update(person(nose=(160, 85)), 1, W, H, 80, 14)
        self.assertEqual((r['level'], r['duration_s']), ('watch', 0))

    def test_board_message_is_compact_ascii(self):
        c = calibrated()
        r = c.update(person(nose=(160, 85)), 1, W, H, 10, 77)
        msg = ps.board_message(r)
        self.assertEqual(msg, 'cam_test pose {"seq":77,"state":"head_down","level":"watch","duration_s":0,"events":[]}\n')
        self.assertNotIn(' ', msg.split(' ', 2)[2].strip())
        self.assertLess(len(msg), 500)


if __name__ == '__main__':
    unittest.main()
