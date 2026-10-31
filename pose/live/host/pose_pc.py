"""PC-side YOLO26-pose on JPEG frames sent by the board."""
import time
from pathlib import Path

MODELS = Path(__file__).resolve().parents[1] / 'models'
ROTATE_CODES = {90: 'ROTATE_90_CLOCKWISE', 180: 'ROTATE_180', 270: 'ROTATE_90_COUNTERCLOCKWISE'}


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match_person(people, board_people):
    """Index of the PC person that is the board's main (highest-score) box, else the largest person."""
    if not people:
        return None
    if board_people:
        main = max(board_people, key=lambda p: p['score'])['box']
        best = max(range(len(people)), key=lambda i: iou(people[i]['box'], main))
        if iou(people[best]['box'], main) > 0.1:
            return best
    return max(range(len(people)), key=lambda i: (people[i]['box'][2] - people[i]['box'][0]) * (people[i]['box'][3] - people[i]['box'][1]))


class PoseRunner:
    def __init__(self, model='yolo26s-pose.pt', device='mps', kpt_conf=0.5):
        self.model_name = model
        self.device = device
        self.kpt_conf = kpt_conf
        self.model = None

    def load(self):
        if self.model is None:
            import torch
            from ultralytics import YOLO
            if self.device == 'mps' and not torch.backends.mps.is_available():
                self.device = 'cpu'
            self.model = YOLO(str(MODELS / self.model_name))
        return self.model

    def run(self, jpeg, rotation):
        import cv2
        import numpy as np
        model = self.load()
        start = time.perf_counter()
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError('JPEG 解码失败')
        if rotation in ROTATE_CODES:
            img = cv2.rotate(img, getattr(cv2, ROTATE_CODES[rotation]))
        decoded = time.perf_counter()
        r = model.predict(img, device=self.device, verbose=False)[0]
        done = time.perf_counter()
        h, w = img.shape[:2]
        people = []
        if r.boxes is not None and len(r.boxes):
            boxes = r.boxes.xyxy.cpu().numpy()
            scores = r.boxes.conf.cpu().numpy()
            kxy = r.keypoints.xy.cpu().numpy()
            kconf = r.keypoints.conf.cpu().numpy() if r.keypoints.conf is not None else None
            for i in range(len(boxes)):
                x0, y0, x1, y1 = boxes[i]
                pts = []
                for j in range(kxy.shape[1]):
                    c = float(kconf[i][j]) if kconf is not None else 1.0
                    x, y = kxy[i][j]
                    pts.append([int(round(x)), int(round(y))] if c >= self.kpt_conf and 0 <= x < w and 0 <= y < h else None)
                people.append({'score': round(float(scores[i]), 4),
                               'box': [int(max(0, x0)), int(max(0, y0)), int(min(w - 1, x1)), int(min(h - 1, y1))],
                               'keypoints': pts,
                               'kpt_conf': [round(float(c), 3) for c in kconf[i]] if kconf is not None else None})
        ok, shown = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return {'width': w, 'height': h, 'people': people, 'decode_ms': round((decoded - start) * 1000, 1),
                'infer_ms': round((done - decoded) * 1000, 1), 'model': self.model_name, 'device': self.device,
                'image_jpeg': shown.tobytes() if ok else None}
