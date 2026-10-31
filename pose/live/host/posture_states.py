"""Rule-based posture states 5-9 on COCO 17-point keypoints, frontal camera.

Thresholds are provisional (docs/VISION-POSE-ARCHITECTURE.md, section 6.2) and
are compared with a personal calibration baseline. Not a medical judgement.
"""
import json
import math
import statistics

NOSE, LEYE, REYE, LEAR, REAR, LSH, RSH, LWR, RWR = 0, 1, 2, 3, 4, 5, 6, 9, 10
PRIORITY = ('head_on_desk', 'head_down', 'head_tilt', 'shoulder_tilt')
LABELS = {'head_on_desk': '趴桌', 'head_down': '低头', 'head_tilt': '歪头', 'shoulder_tilt': '肩膀一高一低',
          'normal': '正常', 'unknown': '无法判断', 'not_calibrated': '未校准', 'no_person': '无人',
          'stretch': '伸懒腰'}
LEVELS = {'ok': '正常', 'watch': '观察中', 'alert': '提醒', 'unknown': '无法判断'}
THRESHOLDS = {'head_down': 0.15, 'head_tilt': 12.0, 'shoulder_tilt': 0.12}


def _angle_delta(a, b):
    return (a - b + 180) % 360 - 180


def features(person, width, height):
    """Shoulder-normalised measurements, or (None, reason) when they cannot be judged."""
    pts = person.get('keypoints') or []

    def p(i):
        q = pts[i] if i < len(pts) else None
        return q if q is not None and 3 < q[0] < width - 4 and 3 < q[1] < height - 4 else None

    ls, rs = p(LSH), p(RSH)
    if ls is None or rs is None:
        return None, '双肩缺失或靠近画面边缘'
    sw = math.dist(ls, rs)
    if sw < max(30, width * 0.10):
        return None, '双肩过近，可能距离过远或身体转向'
    sy = (ls[1] + rs[1]) / 2
    nose = p(NOSE)
    face_missing = sum(1 for i in (NOSE, LEYE, REYE, LEAR, REAR) if p(i) is None)
    f = {'shoulder': (ls[1] - rs[1]) / sw, 'face_missing': face_missing}
    if nose is not None:
        f['head_drop'] = (nose[1] - sy) / sw
    a, b = (p(LEYE), p(REYE)) if p(LEYE) and p(REYE) else (p(LEAR), p(REAR))
    if a is not None and b is not None:
        f['head_tilt_deg'] = math.degrees(math.atan2(a[1] - b[1], a[0] - b[0]))
    lw, rw = p(LWR), p(RWR)
    f['stretch'] = bool(nose and lw and rw and lw[1] < nose[1] - 0.3 * sw and rw[1] < nose[1] - 0.3 * sw)
    f['desk'] = bool((nose is not None and nose[1] >= sy - 0.1 * sw) or face_missing >= 3)
    return f, ''


class PostureClassifier:
    def __init__(self, calibration_samples=3, alert_seconds=30, alert_samples=3, stretch_cooldown=10,
                 thresholds=None):
        self.calibration_samples = calibration_samples
        self.alert_seconds = alert_seconds
        self.alert_samples = alert_samples
        self.stretch_cooldown = stretch_cooldown
        self.thresholds = dict(THRESHOLDS if thresholds is None else thresholds)
        self.reset()

    def reset(self):
        self.baseline = None
        self.samples = []
        self.calibrating = False
        self.since = {}
        self.counts = {}
        self.last_time = None
        self.last_stretch = None

    def start_calibration(self):
        self.reset()
        self.calibrating = True

    def _clear_timers(self):
        self.since.clear()
        self.counts.clear()

    def _result(self, seq, people, state, level, message, levels=None, metrics=None, duration=0, events=()):
        return dict(seq=seq, state=state, level=level, duration_s=round(duration), events=list(events),
                    calibrated=self.baseline is not None, calibrating=self.calibrating, people=people,
                    levels=levels or {k: 'unknown' for k in PRIORITY}, metrics=metrics or {}, message=message)

    def update(self, person, people, width, height, now, seq):
        """person: the matched pose result (or None); people: how many people the PC model saw."""
        if self.last_time is not None and (now < self.last_time or now - self.last_time > 30):
            self._clear_timers()
            if self.calibrating:
                self.samples.clear()
        self.last_time = now
        if person is None:
            self._clear_timers()
            if self.calibrating:
                self.samples.clear()
            return self._result(seq, people, 'no_person', 'unknown', '画面中没有可判断的人')
        f, reason = features(person, width, height)
        if f is None:
            self._clear_timers()
            if self.calibrating:
                self.samples.clear()
            return self._result(seq, people, 'unknown', 'unknown', '无法判断：' + reason)
        events = []
        if f['stretch'] and (self.last_stretch is None or now - self.last_stretch >= self.stretch_cooldown):
            self.last_stretch = now
            events.append('stretch')
        if self.calibrating:
            if 'head_drop' not in f or f['desk']:
                self.samples.clear()
                return self._result(seq, people, 'not_calibrated', 'unknown', '校准需要正对坐好，看得见鼻子和双肩', events=events)
            self.samples.append(f)
            if len(self.samples) < self.calibration_samples:
                return self._result(seq, people, 'not_calibrated', 'unknown',
                                    f'正在校准 {len(self.samples)}/{self.calibration_samples}，请保持舒适坐姿', events=events)
            keys = [k for k in ('head_drop', 'shoulder', 'head_tilt_deg') if all(k in s for s in self.samples)]
            spread = {'head_drop': 0.10, 'shoulder': 0.10, 'head_tilt_deg': 8.0}
            if any(max(s[k] for s in self.samples) - min(s[k] for s in self.samples) > spread[k] for k in keys):
                self.samples.clear()
                return self._result(seq, people, 'not_calibrated', 'unknown', '校准期间姿态变化过大，请保持稳定', events=events)
            self.baseline = {k: statistics.median(s[k] for s in self.samples) for k in keys}
            self.calibrating = False
            return self._result(seq, people, 'normal', 'ok', '校准完成', events=events)
        if self.baseline is None:
            return self._result(seq, people, 'not_calibrated', 'unknown', '未校准：请坐好后点击“校准坐姿”', events=events)

        deltas = {}
        if 'head_drop' in f and 'head_drop' in self.baseline:
            deltas['head_drop'] = f['head_drop'] - self.baseline['head_drop']
        if 'head_tilt_deg' in f and 'head_tilt_deg' in self.baseline:
            deltas['head_tilt_deg'] = _angle_delta(f['head_tilt_deg'], self.baseline['head_tilt_deg'])
        if 'shoulder' in self.baseline:
            deltas['shoulder'] = f['shoulder'] - self.baseline['shoulder']
        abnormal = {
            'head_on_desk': f['desk'],
            'head_down': deltas['head_drop'] > self.thresholds['head_down'] if 'head_drop' in deltas else None,
            'head_tilt': abs(deltas['head_tilt_deg']) > self.thresholds['head_tilt'] if 'head_tilt_deg' in deltas else None,
            'shoulder_tilt': abs(deltas['shoulder']) > self.thresholds['shoulder_tilt'] if 'shoulder' in deltas else None,
        }
        levels, durations = {}, {}
        for key in PRIORITY:
            if abnormal[key] is None:
                self.since.pop(key, None)
                self.counts.pop(key, None)
                levels[key] = 'unknown'
            elif abnormal[key]:
                self.since.setdefault(key, now)
                self.counts[key] = self.counts.get(key, 0) + 1
                durations[key] = now - self.since[key]
                sustained = durations[key] >= self.alert_seconds and self.counts[key] >= self.alert_samples
                levels[key] = 'alert' if sustained else 'watch'
            else:
                self.since.pop(key, None)
                self.counts.pop(key, None)
                levels[key] = 'ok'
        metrics = {k: round(v, 3 if k != 'head_tilt_deg' else 1) for k, v in deltas.items()}
        metrics['face_missing'] = f['face_missing']
        for wanted in ('alert', 'watch'):
            hits = [k for k in PRIORITY if levels[k] == wanted]
            if hits:
                main = max(hits, key=lambda k: (durations[k], -PRIORITY.index(k)))
                return self._result(seq, people, main, wanted, f'{LABELS[main]}：{LEVELS[wanted]} {durations[main]:.0f} 秒',
                                    levels, metrics, durations[main], events)
        if all(v == 'unknown' for v in levels.values()):
            return self._result(seq, people, 'unknown', 'unknown', '无法判断：关键点不足', levels, metrics, events=events)
        return self._result(seq, people, 'normal', 'ok', '接近校准时的坐姿', levels, metrics, events=events)


def board_message(result):
    """Compact ASCII JSON for `cam_test pose`; the board only reads these fields."""
    keep = {k: result[k] for k in ('seq', 'state', 'level', 'duration_s', 'events')}
    return 'cam_test pose ' + json.dumps(keep, separators=(',', ':'), ensure_ascii=True) + '\n'
