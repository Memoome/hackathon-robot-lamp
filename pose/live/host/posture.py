"""Experimental front-view posture trends on COCO 17-point 2D coordinates.

Thresholds are provisional UI parameters, not clinical criteria. No individual
landmark confidence is available in the board protocol.
"""
import math
import statistics

THRESHOLDS = {'shoulder': 0.12, 'head_drop': 0.15, 'torso': 0.18}
LABELS = {'shoulder': '肩部倾斜', 'head_drop': '头部降低', 'torso': '躯干侧倾'}

def measurements(result):
    people = result.get('people', [])
    if len(people) != 1:
        return {}, '需要画面中恰好一人'
    person = people[0]
    if person.get('score', 0) < 0.5:
        return {}, '人体框置信度不足'
    points = person.get('keypoints', [])
    if len(points) != 17:
        return {}, '关键点格式错误'
    width, height = result['width'], result['height']
    def point(i):
        p = points[i]
        if p is None or not (3 < p[0] < width - 4 and 3 < p[1] < height - 4):
            return None
        return p
    left, right, nose = point(5), point(6), point(0)
    if left is None or right is None:
        return {}, '双肩缺失或靠近画面边缘'
    shoulder_width = math.dist(left, right)
    if shoulder_width < max(30, width * .10):
        return {}, '双肩过近，可能距离过远或身体转向'
    sx, sy = (left[0] + right[0]) / 2, (left[1] + right[1]) / 2
    values = {'shoulder': (left[1] - right[1]) / shoulder_width}
    if nose is not None and nose[1] < sy:
        values['head_drop'] = (nose[1] - sy) / shoulder_width
    hip_l, hip_r = point(11), point(12)
    if hip_l is not None and hip_r is not None:
        hx, hy = (hip_l[0]+hip_r[0])/2, (hip_l[1]+hip_r[1])/2
        if hy - sy >= shoulder_width * .3:
            values['torso'] = (sx - hx) / shoulder_width
    return values, ''

class PostureMonitor:
    def __init__(self, calibration_samples=3, delay_seconds=30, thresholds=None):
        self.calibration_samples = calibration_samples
        self.delay_seconds = delay_seconds
        self.thresholds = dict(THRESHOLDS if thresholds is None else thresholds)
        self.reset()

    def reset(self):
        self.baseline = None
        self.samples = []
        self.calibrating = False
        self.since = {}
        self.counts = {}
        self.last_time = None
        self.last_rotation = None

    def start_calibration(self):
        self.reset()
        self.calibrating = True

    def update(self, result, now):
        rotation = result.get('rotation')
        if self.last_rotation is not None and rotation != self.last_rotation:
            self.reset()
            return '方向已改变，请重新校准', {}
        self.last_rotation = rotation
        # Missing samples and long gaps cannot count toward sustained posture.
        if self.last_time is not None and (now < self.last_time or now - self.last_time > 30):
            self.since.clear()
            self.counts.clear()
            if self.calibrating:
                self.samples.clear()
        self.last_time = now
        values, reason = measurements(result)
        if reason:
            self.since.clear()
            self.counts.clear()
            if self.calibrating:
                self.samples.clear()
            return '无法判断：' + reason, {}
        if self.calibrating:
            if 'head_drop' not in values:
                self.samples.clear()
                return '校准需要同时看见鼻子和双肩', {}
            self.samples.append(values)
            if len(self.samples) < self.calibration_samples:
                return f'正在校准 {len(self.samples)}/{self.calibration_samples}，请保持舒适坐姿', {}
            common = set.intersection(*(set(s) for s in self.samples))
            # Reject visibly unstable baseline instead of silently calibrating motion.
            if any(max(s[k] for s in self.samples)-min(s[k] for s in self.samples) > 0.10 for k in common):
                self.samples.clear()
                return '校准期间姿态变化过大，请保持稳定', {}
            self.baseline = {k: statistics.median(s[k] for s in self.samples) for k in common}
            self.calibrating = False
            return '校准完成；仅监测校准时可见的指标', {}
        if self.baseline is None:
            return '未校准：请坐稳并点击“校准坐姿”', {}
        details = {}
        for key in LABELS:
            if key not in values or key not in self.baseline:
                self.since.pop(key, None)
                self.counts.pop(key, None)
                details[key] = '无法判断'
                continue
            delta = values[key] - self.baseline[key]
            abnormal = delta > self.thresholds[key] if key == 'head_drop' else abs(delta) > self.thresholds[key]
            if abnormal:
                self.since.setdefault(key, now)
                self.counts[key] = self.counts.get(key, 0) + 1
                duration = now - self.since[key]
                details[key] = ('持续提醒' if duration >= self.delay_seconds and self.counts[key] >= 3 else '观察中') + f' {duration:.0f}秒'
            else:
                self.since.pop(key, None)
                self.counts.pop(key, None)
                details[key] = '接近基线'
        return ' | '.join(f'{LABELS[k]}：{details[k]}' for k in LABELS), details
