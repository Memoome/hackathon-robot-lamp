"""Scene-labelled accuracy test: the person says what is in front of the camera, the
board's detections and the PC's pose results are scored against that."""
import json
import math
import statistics
import time
from datetime import datetime

SCENES = {
    'empty': ('无人（空座位）', 0),
    'near': ('正对坐着 · 近（约 50 厘米）', 1),
    'far': ('正对坐着 · 稍远（约 1.5 米）', 1),
    'posture': ('低头、侧身、托腮', 1),
    'leave_return': ('起身离开再回来', None),
}
TARGET_SECONDS = 60


def _pct(n, d):
    return round(100 * n / d, 1) if d else None


def scene_metrics(key, dets, poses, marks):
    label, expected = SCENES[key]
    m = {'scene': key, 'label': label, 'expected_people': expected, 'frames': len(dets)}
    if dets:
        m['seconds'] = round((dets[-1]['t_ms'] - dets[0]['t_ms']) / 1000, 1)
    with_person = [d for d in dets if d['people']]
    if expected == 0:
        m['false_alarm_pct'] = _pct(len(with_person), len(dets))
    elif expected == 1:
        m['detected_pct'] = _pct(len(with_person), len(dets))
        m['multi_pct'] = _pct(sum(1 for d in dets if len(d['people']) > 1), len(dets))
        mains = [max(d['people'], key=lambda p: p['score']) for d in with_person]
        if mains:
            m['score_mean'] = round(statistics.mean(p['score'] for p in mains), 3)
            m['score_min'] = round(min(p['score'] for p in mains), 3)
        if len(mains) >= 2:
            cx = [p['center'][0] for p in mains]
            cy = [p['center'][1] for p in mains]
            m['center_std_px'] = [round(statistics.pstdev(cx), 1), round(statistics.pstdev(cy), 1)]
            mx, my = statistics.median(cx), statistics.median(cy)
            dev = sorted(math.hypot(x - mx, y - my) for x, y in zip(cx, cy))
            m['center_p95_px'] = round(dev[min(len(dev) - 1, int(0.95 * len(dev)))], 1)
    if key == 'leave_return':
        reactions = []
        for mark in marks:
            want_person = mark['event'] == 'return'
            hit = next((d for d in dets if d['host_rx'] >= mark['host'] and bool(d['people']) == want_person), None)
            reactions.append({'event': mark['event'], 'seconds': round(hit['host_rx'] - mark['host'], 2) if hit else None})
        m['reactions'] = reactions
    m['pose_frames'] = len(poses)
    if poses:
        m['pose_person_pct'] = _pct(sum(1 for p in poses if p['matched']), len(poses))
        states = {}
        for p in poses:
            states[p['state']] = states.get(p['state'], 0) + 1
        m['pose_states'] = states
    return m


class SceneRecorder:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.reset()

    def reset(self):
        self.current = None
        self.started = None
        self.records = {}

    def start(self, key):
        if key not in SCENES:
            raise ValueError('未知场景。')
        self.current = key
        self.started = self.clock()
        self.records[key] = {'dets': [], 'poses': [], 'marks': []}

    def end(self):
        self.current = None
        self.started = None

    def mark(self, event):
        if self.current != 'leave_return' or event not in ('leave', 'return'):
            raise ValueError('只有“起身离开再回来”场景可以标记离开或回来。')
        self.records[self.current]['marks'].append({'event': event, 'host': self.clock()})

    def on_det(self, det):
        if self.current:
            self.records[self.current]['dets'].append(
                {'seq': det['seq'], 't_ms': det['t_ms'], 'host_rx': det.get('host_rx', self.clock()),
                 'people': [{'score': p['score'], 'center': p['center']} for p in det['people']]})

    def on_pose(self, seq, verdict, matched):
        if self.current:
            self.records[self.current]['poses'].append(
                {'seq': seq, 'state': verdict['state'], 'level': verdict['level'], 'matched': matched})

    def results(self):
        return [scene_metrics(k, r['dets'], r['poses'], r['marks']) for k, r in self.records.items()]

    def status(self):
        return {'current': self.current, 'elapsed': None if self.started is None else round(self.clock() - self.started, 1),
                'target_seconds': TARGET_SECONDS, 'scenes': {k: v[0] for k, v in SCENES.items()},
                'results': self.results()}

    def save(self, folder, device_note=''):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('scene-test-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.json')
        path.write_text(json.dumps({'saved_at': datetime.now().isoformat(timespec='seconds'), 'note': device_note,
                                    'results': self.results(), 'records': self.records},
                                   ensure_ascii=False, indent=1), encoding='utf-8')
        return path
