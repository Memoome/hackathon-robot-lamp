"""Loopback-only camera viewer. One worker owns the serial connection."""
import argparse
import base64
import collections
import json
import queue
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import camera_wire as wire
import live_pose as live
import pose_pc
import posture
import posture_states
import scene_test

PAGE = Path(__file__).resolve().parents[1] / 'web' / 'index.html'


def failure_message(error):
    if 'capture_removed' in error:
        return '当前固件已移除板端姿态模型（P3），请改用“人体检测”模式；姿态在电脑端做。'
    if 'Camera sensor is not BF3901' in error:
        return '开发板已返回错误：摄像头型号读取异常，采集已停止。详情包含实际型号；反复重连不能保证恢复。'
    if 'CAM_ERROR' in error and 'ESP_ERR_TIMEOUT' in error:
        return '开发板已返回错误：摄像头取帧超时，未获得有效图像。这不是网页断联；采集已停止。'
    if 'CAM_ERROR' in error and 'ESP_FAIL' in error:
        return '开发板已返回错误：摄像头初始化或采集失败。这不是网页断联；请查看错误详情。'
    return '采集已中断。请查看错误详情，准备好后重新连接。'


class Camera:
    def __init__(self, session=live.session, stream=live.stream_session, pose_runner=None):
        self.session = session
        self.stream = stream
        self.pose_runner = pose_runner or pose_pc.PoseRunner()
        self.preview_every = 10
        self.auto_snap = 0
        self.reset_detections()
        self.lock = threading.RLock()
        self.commands = queue.Queue()
        self.pose_jobs = queue.Queue(maxsize=1)
        self.classifier = posture_states.PostureClassifier()
        self.pc_pose = None
        self.pose_rx = None
        self.pose_error = None
        self.board_warning = None
        self.pose_sent = {}
        self.image_mime = 'image/png'
        self.scenes = scene_test.SceneRecorder()
        threading.Thread(target=self.pose_loop, daemon=True).start()
        self.worker = None
        self.cancel = threading.Event()
        self.active = False
        self.phase = 'idle'
        self.message = '准备就绪，点击开始查看。'
        self.error = None
        self.frame = None
        self.pending_frame = None
        self.pose_result = None
        self.image_url = None
        self.raw_image_url = None
        self.png = None
        self.version = 0
        self.count = 0
        self.updated = None
        self.interval = None
        self.inference_ms = None
        self.last_seen = time.monotonic()
        self.rotation = 90
        self.mode = 'pose'
        self.monitor = posture.PostureMonitor()
        self.set_posture('坐姿实验功能：先开始查看，再校准坐姿。仅供姿态变化提醒。')

    def reset_detections(self):
        self.dets = collections.deque(maxlen=60)
        self.det_count = 0
        self.stats = None
        self.presence = None
        self.presence_calib = None
        self.presence_events = collections.deque(maxlen=20)
        # Smallest (host receive time - board result time) seen; maps board ms onto host seconds.
        self.clock_offset = None

    def detection_status(self):
        dets = list(self.dets)
        rate = None
        if len(dets) >= 2 and dets[-1]['t_ms'] > dets[0]['t_ms']:
            rate = (len(dets)-1) * 1000 / (dets[-1]['t_ms']-dets[0]['t_ms'])
        def avg(key):
            return sum(d[key] for d in dets) / len(dets) if dets else None
        return dict(det_count=self.det_count, det_rate=rate, infer_avg=avg('infer_ms'),
                    prep_avg=avg('prep_ms'), window=len(dets), stats=self.stats,
                    latest=dets[-1] if dets else None, preview_every=self.preview_every,
                    auto_snap=self.auto_snap)

    def set_posture(self, summary, details=None, frame_id=None):
        self.posture = dict(summary=summary, details=details or {}, frame_id=frame_id,
                            updated=time.time() if frame_id is not None else None)

    def posture_status(self):
        with self.lock:
            if self.mode == 'detect':
                c = self.classifier
                r = self.pc_pose['posture'] if self.pc_pose else None
                age = None if not self.pc_pose else max(0, time.time()-self.pc_pose['updated'])
                details = {k: posture_states.LEVELS[r['levels'][k]] for k in posture_states.PRIORITY} if r else {}
                return dict(summary=r['message'] if r else '先开始查看，再点“校准坐姿”。姿态由电脑端 YOLO26 判断。',
                            details=details, frame_id=r['seq'] if r else None, age=age,
                            labels={k: posture_states.LABELS[k] for k in posture_states.PRIORITY},
                            calibrating=c.calibrating, calibrated=c.baseline is not None, baseline=c.baseline,
                            state=r['state'] if r else None, level=r['level'] if r else None,
                            stale=age is not None and (not self.active or age > 30))
            age = None if self.posture['updated'] is None else max(0, time.time()-self.posture['updated'])
            return dict(self.posture, labels=posture.LABELS, age=age,
                        calibrating=self.monitor.calibrating,
                        calibrated=self.monitor.baseline is not None,
                        baseline=self.monitor.baseline,
                        stale=age is not None and (not self.active or age > 30))

    def calibrate(self):
        with self.lock:
            if not self.active:
                raise ValueError('请先开始查看，再校准坐姿。')
            if self.mode == 'detect':
                self.classifier.start_calibration()
                # The board records its own box baseline (too close / standing) at the same moment.
                self.presence_calib = None
                self.commands.put(b'cam_test calib\n')
                if self.auto_snap:
                    self.commands.put(b'cam_test snap\n')
                return
            self.monitor.start_calibration()
            self.set_posture(f'校准中：请保持舒适坐姿，等待 {self.monitor.calibration_samples} 次有效结果。')

    def status(self, heartbeat=False):
        with self.lock:
            if heartbeat:
                self.last_seen = time.monotonic()
            age = None if self.updated is None else max(0, time.time()-self.updated)
            return dict(active=self.active, phase=self.phase, message=self.message,
                        error=self.error, version=self.version, count=self.count,
                        updated=self.updated, age=age, stale=self.png is not None and
                        (not self.active or age > 30), interval=self.interval,
                        inference_ms=self.inference_ms, rotation=self.rotation,
                        mode=self.mode, detection=self.detection_status(),
                        result=self.pose_result, image_url=self.image_url,
                        raw_image_url=self.raw_image_url,
                        has_frame=self.png is not None,
                        frame_id=self.frame['id'] if self.frame else None,
                        width=self.frame['w'] if self.frame else None,
                        height=self.frame['h'] if self.frame else None,
                        posture=self.posture_status(),
                        pc_pose={k: v for k, v in self.pc_pose.items() if k != 'image'} if self.pc_pose else None,
                        pose_rx=self.pose_rx, pose_error=self.pose_error, board_warning=self.board_warning,
                        presence=self.presence, presence_calib=self.presence_calib,
                        presence_events=list(self.presence_events),
                        scene=self.scenes.status())

    def emit(self, kind, value):
        with self.lock:
            if kind == 'status':
                self.message = value
                self.phase = 'waiting'
            elif kind == 'det':
                if self.cancel.is_set():
                    return
                self.dets.append(value)
                self.scenes.on_det(value)
                self.det_count += 1
                self.pose_result = value
                self.inference_ms = value['infer_ms']
                if 'host_rx' in value:
                    est = value['host_rx'] - (value['t_ms'] + value['prep_ms'] + value['infer_ms']) / 1000
                    self.clock_offset = est if self.clock_offset is None else min(self.clock_offset, est)
                self.phase = 'streaming'
                self.message = (f'板端连续检测中；有人且稳定时每 {self.auto_snap} 秒自动传图到电脑做姿态推理。' if self.auto_snap else
                                '板端连续检测中；画面按设定间隔传到电脑做姿态推理。' if self.preview_every else '板端连续检测中；画面传输已关闭。')
            elif kind == 'stats':
                self.stats = value
            elif kind == 'presence':
                if value.get('event'):
                    self.presence_events.append(dict(event=value['event'], seq=value['seq'], at=time.time()))
                self.presence = dict(value, updated=time.time())
            elif kind == 'presence_calib':
                self.presence_calib = value
            elif kind == 'jpeg':
                if self.cancel.is_set():
                    return
                try:
                    self.pose_jobs.get_nowait()
                except queue.Empty:
                    pass
                self.pose_jobs.put_nowait(value)
            elif kind == 'pose_rx':
                sent = self.pose_sent.get(value.get('seq'))
                self.pose_rx = dict(value, ack_ms=round((time.monotonic()-sent)*1000, 1) if sent else None)
            elif kind == 'board_warning':
                self.board_warning = value
            elif kind == 'frame':
                if self.cancel.is_set():
                    return
                self.pending_frame = (value, time.time())
                if self.png is None:
                    self.phase = 'waiting'
                self.message = '已收到新画面，正在推理；显示区保留上一帧完整结果。'
            elif kind == 'result':
                if self.cancel.is_set():
                    return
                if self.pending_frame is None or value is not self.pending_frame[0]:
                    raise ValueError('推理结果没有对应的待处理画面')
                result = live.validate_result(value['result'], value, self.mode)
                now = self.pending_frame[1]
                self.interval = None if self.count == 0 else now-self.updated
                self.frame = value
                self.pose_result = result
                self.png = wire.png(value['rgb'], value['w'], value['h'])
                annotated = wire.png(live.overlay(value), value['w'], value['h'])
                self.raw_image_url = 'data:image/png;base64,' + base64.b64encode(self.png).decode()
                self.image_url = 'data:image/png;base64,' + base64.b64encode(annotated).decode()
                self.updated = now
                self.version += 1
                self.count += 1
                self.inference_ms = result['inference_ms']
                if self.mode == 'pose':
                    summary, details = self.monitor.update(result, time.monotonic())
                    self.set_posture(summary, details, result['id'])
                self.pending_frame = None
                self.phase = 'streaming'
                self.message = '画面与推理结果已同步，正在采集下一帧。'

    def pose_loop(self):
        """Runs PC-side pose on the newest board JPEG; older frames waiting here are dropped."""
        while True:
            frame = self.pose_jobs.get()
            try:
                res = self.pose_runner.run(frame['data'], frame['rotation'])
            except Exception as exc:
                with self.lock:
                    self.pose_error = f'电脑端姿态推理失败：{exc}'
                continue
            done = time.monotonic()
            with self.lock:
                if self.cancel.is_set() or not self.active:
                    continue
                det = frame.get('det') or next((d for d in self.dets if d['seq'] == frame['seq']), None)
                board_people = det['people'] if det else []
                idx = pose_pc.match_person(res['people'], board_people)
                person = res['people'][idx] if idx is not None else None
                verdict = self.classifier.update(person, len(res['people']), res['width'], res['height'], done, frame['seq'])
                self.scenes.on_pose(frame['seq'], verdict, idx is not None)
                capture = None if self.clock_offset is None else frame['t_ms'] / 1000 + self.clock_offset
                def ms(a, b):
                    return None if a is None or b is None else round(max(0.0, b - a) * 1000, 1)
                now = time.time()
                self.interval = None if not self.pc_pose else now - self.pc_pose['updated']
                self.pc_pose = dict(seq=frame['seq'], reason=frame.get('reason'), people=res['people'], main=idx,
                                    board_people=board_people, width=res['width'], height=res['height'],
                                    infer_ms=res['infer_ms'], decode_ms=res['decode_ms'], model=res['model'],
                                    device=res['device'], jpeg_bytes=frame['bytes'], enc_ms=frame.get('enc_ms'),
                                    quality=frame.get('quality'), board_to_pc_ms=ms(capture, frame['host_rx']),
                                    pc_ms=ms(frame['host_rx'], done), end_to_end_ms=ms(capture, done),
                                    posture=verdict, updated=now)
                self.pose_error = None
                if res['image_jpeg']:
                    self.png = res['image_jpeg']
                    self.image_mime = 'image/jpeg'
                    self.raw_image_url = self.image_url = 'data:image/jpeg;base64,' + base64.b64encode(self.png).decode()
                self.frame = {'id': frame['seq'], 'w': res['width'], 'h': res['height']}
                self.updated = now
                self.version += 1
                self.count += 1
                self.pose_sent[frame['seq']] = time.monotonic()
                for old in [k for k in self.pose_sent if k < frame['seq'] - 200]:
                    del self.pose_sent[old]
                self.commands.put(posture_states.board_message(verdict).encode())
                # Auto mode sends a frame every few seconds; ask for the next one now so calibration is quick.
                if self.auto_snap and self.classifier.calibrating:
                    self.commands.put(b'cam_test snap\n')

    def scene(self, data):
        action = data.get('action')
        with self.lock:
            if action == 'start':
                if not self.active or self.mode != 'detect':
                    raise ValueError('请先在人体检测模式下开始查看。')
                self.scenes.start(data.get('scene'))
            elif action == 'end':
                self.scenes.end()
            elif action == 'mark':
                self.scenes.mark(data.get('event'))
            elif action == 'reset':
                self.scenes.reset()
            elif action == 'save':
                if not self.scenes.records:
                    raise ValueError('还没有录制任何场景。')
                path = self.scenes.save(live.ROOT / 'evidence', f'preview_every={self.preview_every} rotation={self.rotation}')
                return path.name
            else:
                raise ValueError('未知操作。')

    def sit_limits(self, watch, alert):
        """Shortens the board's sedentary thresholds (seconds) for testing; cleared on board restart."""
        if type(watch) is not int or type(alert) is not int or not 1 <= watch <= alert <= 24 * 3600:
            raise ValueError('久坐阈值需满足 1 ≤ 观察 ≤ 提醒 ≤ 86400 秒。')
        with self.lock:
            if not self.active or self.mode != 'detect':
                raise ValueError('请先在人体检测模式下开始查看。')
            self.commands.put(f'cam_test sit_limits {watch} {alert}\n'.encode())

    def snap(self):
        with self.lock:
            if not self.active or self.mode != 'detect':
                raise ValueError('请先在人体检测模式下开始查看。')
            self.commands.put(b'cam_test snap\n')

    def start(self, rotation=90, mode='pose', preview_every=10, auto_snap=0):
        if type(rotation) is not int or rotation not in (0, 90, 180, 270):
            raise ValueError('方向只能是 0、90、180 或 270 度。')
        if mode not in live.MODES:
            raise ValueError('模式只能是 pose 或 detect。')
        if type(preview_every) is not int or not 0 <= preview_every <= 1000:
            raise ValueError('预览间隔只能是 0 到 1000 帧。')
        if type(auto_snap) is not int or not 0 <= auto_snap <= 600:
            raise ValueError('自动传图间隔只能是 0 到 600 秒。')
        with self.lock:
            if self.active or (self.worker and self.worker.is_alive()):
                return False
            self.cancel = threading.Event()
            self.active = True
            self.phase = 'connecting'
            self.message = '正在连接开发板…'
            self.error = None
            self.rotation = rotation
            self.mode = mode
            self.preview_every = preview_every
            self.auto_snap = auto_snap if mode == 'detect' else 0
            self.reset_detections()
            self.count = 0
            self.pending_frame = None
            self.interval = self.inference_ms = None
            self.monitor.reset()
            self.classifier.reset()
            self.pc_pose = self.pose_rx = self.pose_error = self.board_warning = None
            self.pose_sent = {}
            for q in (self.commands, self.pose_jobs):
                while not q.empty():
                    q.get_nowait()
            self.set_posture('请坐稳并点击“校准坐姿”；重新开始后需要重新校准。')
            self.last_seen = time.monotonic()
            self.worker = threading.Thread(target=self.run, daemon=True)
            self.worker.start()
            return True

    def run(self):
        try:
            if self.mode == 'detect':
                self.stream(self.cancel, self.emit, rotation=self.rotation, preview_every=self.preview_every,
                            commands=self.commands, auto_snap=self.auto_snap)
            else:
                self.session(self.cancel, self.emit, rotation=self.rotation, count=0, save=False, mode=self.mode)
        except Exception as exc:
            with self.lock:
                self.phase = 'error'
                self.error = str(exc)
                self.message = failure_message(self.error)
        finally:
            with self.lock:
                self.active = False
                self.monitor.reset()
                self.set_posture('已停止：坐姿校准已清除，重新开始后需重新校准。')
                if self.phase != 'error':
                    self.phase = 'idle'
                    self.message = '已停止，串口已释放。'

    def stop(self, message='正在停止；等待本轮处理结束后释放串口…'):
        with self.lock:
            if self.active:
                self.cancel.set()
                self.phase = 'stopping'
                self.message = message

    def expire_viewer(self):
        with self.lock:
            if self.active and time.monotonic()-self.last_seen > 30:
                self.stop('网页已离线，正在自动停止采集…')

    def image(self):
        with self.lock:
            return self.png, self.image_mime


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith('POST'):
            super().log_message(fmt, *args)

    def reply(self, status, body, kind='application/json; charset=utf-8', download=False):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; frame-ancestors 'none'")
        if download:
            ext = 'jpg' if kind == 'image/jpeg' else 'png'
            self.send_header('Content-Disposition', f'attachment; filename="camera-frame.{ext}"')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def allowed(self):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        return self.headers.get('Host') in hosts and (
            not self.headers.get('Origin') or self.headers['Origin'] in {'http://'+h for h in hosts})

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {'error': '仅允许本机同源访问。'})
        path = urlsplit(self.path).path
        if path == '/':
            return self.reply(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
        if path == '/api/state':
            return self.reply(200, self.server.camera.status(heartbeat=True))
        if path == '/api/posture':
            return self.reply(200, self.server.camera.posture_status())
        if path == '/api/presence':
            st = self.server.camera.status()
            return self.reply(200, dict(presence=st['presence'], calib=st['presence_calib'],
                                        events=st['presence_events'], active=st['active']))
        if path in ('/frame.png', '/snapshot.png'):
            image, mime = self.server.camera.image()
            if image is None:
                return self.reply(404, {'error': '尚未收到校验通过的新画面。'})
            return self.reply(200, image, mime, download=path == '/snapshot.png')
        return self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        if not self.allowed():
            return self.reply(403, {'error': '仅允许本机同源操作。'})
        if self.headers.get_content_type() != 'application/json':
            return self.reply(415, {'error': '需要 JSON 请求。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024:
                raise ValueError('请求长度无效。')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('请求格式无效。')
            path = urlsplit(self.path).path
            if path == '/api/start':
                started = self.server.camera.start(data.get('rotation', 90), data.get('mode', 'pose'),
                                                   data.get('preview_every', 10), data.get('auto_snap', 0))
                return self.reply(200 if started else 409, self.server.camera.status())
            if path == '/api/stop':
                self.server.camera.stop()
                return self.reply(200, self.server.camera.status())
            if path == '/api/calibrate':
                self.server.camera.calibrate()
                return self.reply(200, self.server.camera.status())
            if path == '/api/sit_limits':
                self.server.camera.sit_limits(data.get('watch'), data.get('alert'))
                return self.reply(200, self.server.camera.status())
            if path == '/api/snap':
                self.server.camera.snap()
                return self.reply(200, self.server.camera.status())
            if path == '/api/scene':
                saved = self.server.camera.scene(data)
                return self.reply(200, dict(self.server.camera.status(), saved=saved))
            return self.reply(404, {'error': 'Not found'})
        except (ValueError, TypeError) as exc:
            return self.reply(400, {'error': str(exc)})


def make_server(port=8767, camera=None):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.camera = camera or Camera()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    server = make_server(args.port)
    done = threading.Event()
    def watchdog():
        while not done.wait(1):
            server.camera.expire_viewer()
    threading.Thread(target=watchdog, daemon=True).start()
    def shutdown(*_):
        server.camera.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(f'Camera viewer: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    finally:
        done.set()
        server.camera.stop()
        if server.camera.worker:
            server.camera.worker.join(timeout=65)
        server.server_close()


if __name__ == '__main__':
    main()
