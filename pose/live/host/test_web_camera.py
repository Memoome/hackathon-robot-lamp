import json
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import web_camera as web


def sample_frame():
    return dict(w=2, h=1, rgb=bytes([0, 0, 0, 255, 255, 255]), id=1, rotation=90, result=dict(id=1,rotation=90,width=320,height=240,inference_ms=7200,people=[]))

def completed_frame(emit):
    frame=sample_frame()
    emit('frame', frame)
    emit('result', frame)

def seated_frame(i):
    points=[None]*17
    points[0],points[5],points[6]=[160,70],[200,120],[120,120]
    person=dict(box=[100,40,220,230],score=0.9,keypoints=points)
    frame=sample_frame()
    frame['id']=frame['result']['id']=i
    frame['result']['people']=[person]
    return frame


class CameraTests(unittest.TestCase):
    def test_results_are_published_atomically_and_waiting_keeps_old_pose(self):
        camera = web.Camera()
        frame = sample_frame()
        camera.emit('frame', frame)
        self.assertFalse(camera.status()['has_frame'])
        camera.emit('result', frame)
        state = camera.status()
        self.assertEqual(state['result']['id'], 1)
        self.assertTrue(state['image_url'].startswith('data:image/png;base64,'))
        camera.emit('frame', sample_frame())
        self.assertEqual(camera.status()['version'], state['version'])
        self.assertEqual(camera.status()['image_url'], state['image_url'])
        with self.assertRaises(ValueError):
            camera.emit('result', sample_frame())

    def test_board_failures_are_not_reported_as_web_disconnects(self):
        self.assertIn('型号读取异常', web.failure_message('Camera sensor is not BF3901, PID=0x1d01\nCAM_ERROR rc=-1'))
        self.assertIn('取帧超时', web.failure_message('CAM_ERROR reason=ESP_ERR_TIMEOUT'))
        self.assertIn('初始化或采集失败', web.failure_message('CAM_ERROR reason=ESP_FAIL'))
        self.assertNotIn('开发板已返回', web.failure_message('Serial port disconnected'))

    def test_only_one_worker_and_stop_releases_it(self):
        called = threading.Event()
        def session(stop, emit, **kwargs):
            self.assertEqual(kwargs['save'], False)
            completed_frame(emit)
            called.set()
            stop.wait(2)
        camera = web.Camera(session)
        self.assertTrue(camera.start())
        self.assertTrue(called.wait(1))
        self.assertFalse(camera.start())
        camera.stop()
        camera.worker.join(1)
        state = camera.status()
        self.assertFalse(state['active'])
        self.assertTrue(state['stale'])
        self.assertEqual(state['count'], 1)
        self.assertTrue(camera.image()[0].startswith(b'\x89PNG'))

    def test_detect_mode_reaches_session_and_skips_posture(self):
        seen = {}
        def stream(stop, emit, **kwargs):
            seen.update(kwargs)
            for seq, t in ((1, 1000), (2, 1160), (3, 1330)):
                emit('det', dict(seq=seq, id=seq, t_ms=t, infer_ms=118.0, prep_ms=32.0, cycle_ms=165.0,
                                 width=320, height=240, rotation=90, people=[], mode='detect'))
            stop.wait(2)
        def session(stop, emit, **kwargs):
            raise AssertionError('detect mode must use the stream path')
        camera = web.Camera(session, stream)
        with self.assertRaises(ValueError):
            camera.start(90, 'bogus')
        with self.assertRaises(ValueError):
            camera.start(90, 'detect', -1)
        self.assertTrue(camera.start(90, 'detect', 0))
        for _ in range(100):
            if camera.status()['detection']['det_count'] == 3:
                break
            time.sleep(0.01)
        state = camera.status()
        self.assertEqual(state['detection']['det_count'], 3)
        self.assertAlmostEqual(state['detection']['det_rate'], 2 * 1000 / 330, places=3)
        self.assertEqual(state['detection']['infer_avg'], 118.0)
        self.assertEqual(state['result']['seq'], 3)
        camera.stop()
        camera.worker.join(1)
        self.assertEqual((seen['rotation'], seen['preview_every']), (90, 0))
        self.assertIs(seen['commands'], camera.commands)
        self.assertEqual(camera.status()['mode'], 'detect')

    def test_presence_auto_snap_and_board_calibration(self):
        seen = {}
        def stream(stop, emit, **kwargs):
            seen.update(kwargs)
            stop.wait(5)
        camera = web.Camera(lambda *a, **k: None, stream)
        with self.assertRaises(ValueError):
            camera.start(90, 'detect', 0, 601)
        self.assertTrue(camera.start(90, 'detect', 0, 3))
        for _ in range(100):
            if seen:
                break
            time.sleep(0.01)
        self.assertEqual((seen['preview_every'], seen['auto_snap']), (0, 3))
        self.assertEqual(camera.status()['detection']['auto_snap'], 3)
        camera.calibrate()
        self.assertEqual([camera.commands.get_nowait() for _ in range(2)], [b'cam_test calib\n', b'cam_test snap\n'])
        with self.assertRaises(ValueError):
            camera.sit_limits(90, 60)
        camera.sit_limits(60, 90)
        self.assertEqual(camera.commands.get_nowait(), b'cam_test sit_limits 60 90\n')
        states = {'away': True, 'sedentary': 'ok', 'too_close': 'unknown', 'standing': False}
        camera.emit('presence', dict(seq=5, t_ms=1, present=False, sit_s=0, states=states, event='leave'))
        camera.emit('presence', dict(seq=6, t_ms=2, present=False, sit_s=0, states=states, event=None))
        camera.emit('presence_calib', {'ok': True, 'seq': 6, 'area': 18000})
        state = camera.status()
        self.assertEqual(state['presence']['seq'], 6)
        self.assertEqual([e['event'] for e in state['presence_events']], ['leave'])
        self.assertTrue(state['presence_calib']['ok'])
        camera.stop()
        camera.worker.join(1)
        self.assertTrue(camera.start(90, 'detect', 10))
        self.assertIsNone(camera.status()['presence'])
        camera.stop()
        camera.worker.join(1)

    def test_scene_recording_needs_detect_stream_and_scores_detections(self):
        camera = web.Camera(lambda *a, **k: None, lambda stop, emit, **k: stop.wait(5))
        with self.assertRaises(ValueError):
            camera.scene({'action': 'start', 'scene': 'near'})
        camera.start(90, 'detect', 0)
        camera.scene({'action': 'start', 'scene': 'near'})
        for seq, people in ((1, [{'score': .9, 'box': [0, 0, 9, 9], 'center': [5, 5]}]), (2, [])):
            camera.emit('det', dict(seq=seq, id=seq, t_ms=seq * 160, infer_ms=118.0, prep_ms=32.0, cycle_ms=160.0,
                                    width=320, height=240, rotation=90, people=people, mode='detect'))
        camera.scene({'action': 'end'})
        result = camera.status()['scene']['results'][0]
        self.assertEqual((result['scene'], result['frames'], result['detected_pct']), ('near', 2, 50.0))
        with self.assertRaises(ValueError):
            camera.scene({'action': 'mark', 'event': 'leave'})
        camera.stop()
        camera.worker.join(1)

    def test_board_jpeg_runs_pc_pose_and_sends_verdict_back(self):
        class FakeRunner:
            def run(self, jpeg, rotation):
                pts = [None] * 17
                pts[0], pts[1], pts[2] = [160, 70], [172, 62], [148, 62]
                pts[5], pts[6] = [200, 120], [120, 120]
                return {'width': 320, 'height': 240, 'infer_ms': 40.0, 'decode_ms': 1.0, 'model': 'fake',
                        'device': 'cpu', 'image_jpeg': b'\xff\xd8fake',
                        'people': [{'score': .9, 'box': [100, 20, 220, 239], 'keypoints': pts}]}
        camera = web.Camera(lambda *a, **k: None, lambda stop, emit, **k: stop.wait(5), FakeRunner())
        camera.start(90, 'detect', 10)
        det = dict(seq=7, id=7, t_ms=1000, infer_ms=118.0, prep_ms=32.0, cycle_ms=165.0, width=320, height=240,
                   rotation=90, people=[{'score': .9, 'box': [102, 22, 218, 239], 'center': [160, 130]}],
                   mode='detect', host_rx=50.15)
        camera.emit('det', det)
        camera.calibrate()
        self.assertEqual(camera.commands.get_nowait(), b'cam_test calib\n')
        for _ in range(3):
            camera.emit('jpeg', dict(seq=7, t_ms=1000, bytes=4, data=b'\xff\xd8xx', rotation=90, host_rx=50.4,
                                     det=det, enc_ms=33.0, quality=80, reason='preview'))
            for _ in range(200):
                if camera.commands.qsize():
                    break
                time.sleep(0.01)
            camera.commands.get_nowait()
        state = camera.status()
        self.assertEqual(state['pc_pose']['main'], 0)
        # offset = 50.15 - (1000+32+118)/1000 = 49.0, capture = 1.0 + 49.0, received at 50.4
        self.assertEqual(state['pc_pose']['board_to_pc_ms'], 400.0)
        self.assertTrue(state['posture']['calibrated'])
        self.assertTrue(state['image_url'].startswith('data:image/jpeg;base64,'))
        camera.emit('pose_rx', {'seq': 7, 'state': 'normal', 'level': 'ok', 'stale': 0, 'count': 3})
        self.assertIsNotNone(camera.status()['pose_rx']['ack_ms'])
        camera.stop()
        camera.worker.join(1)

    def test_failure_preserves_frame_but_never_calls_it_live(self):
        def session(stop, emit, **kwargs):
            completed_frame(emit)
            raise RuntimeError('sensor timeout')
        camera = web.Camera(session)
        camera.start()
        camera.worker.join(1)
        state = camera.status()
        self.assertEqual(state['phase'], 'error')
        self.assertEqual(state['error'], 'sensor timeout')
        self.assertTrue(state['stale'])
        self.assertFalse(state['active'])

    def test_posture_follows_results_and_calibration(self):
        camera = web.Camera()
        with self.assertRaises(ValueError):
            camera.calibrate()
        camera.active = True
        camera.calibrate()
        self.assertTrue(camera.posture_status()['calibrating'])
        for i in range(1, 4):
            frame = seated_frame(i)
            camera.emit('frame', frame)
            camera.emit('result', frame)
        state = camera.posture_status()
        self.assertTrue(state['calibrated'])
        self.assertEqual(state['frame_id'], 3)
        self.assertIn('校准完成', state['summary'])
        frame = seated_frame(4)
        camera.emit('frame', frame)
        camera.emit('result', frame)
        state = camera.status()['posture']
        self.assertEqual(state['details']['shoulder'], '接近基线')
        self.assertEqual(state['details']['torso'], '无法判断')

    def test_posture_needs_exactly_one_person(self):
        camera = web.Camera()
        completed_frame(camera.emit)
        self.assertIn('恰好一人', camera.posture_status()['summary'])

    def test_viewer_timeout_requests_stop(self):
        camera = web.Camera()
        camera.active = True
        camera.last_seen = time.monotonic()-31
        camera.expire_viewer()
        self.assertTrue(camera.cancel.is_set())


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.camera = web.Camera(lambda stop, emit, **kwargs: stop.wait(2))
        self.server = web.make_server(0, self.camera)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.camera.stop()
        if self.camera.worker:
            self.camera.worker.join(3)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)

    def request(self, path, data=None, **headers):
        if data is not None:
            headers.setdefault('Content-Type', 'application/json')
            data = json.dumps(data).encode()
        return urlopen(Request(self.url+path, data=data, headers=headers), timeout=3)

    def test_routes_do_not_open_serial_and_no_fake_picture(self):
        with self.request('/') as response:
            self.assertIn('摄像头预览', response.read().decode())
        with self.request('/api/state') as response:
            self.assertFalse(json.load(response)['has_frame'])
        with self.assertRaises(HTTPError) as exc:
            self.request('/frame.png')
        self.assertEqual(exc.exception.code, 404)
        self.assertIsNone(self.camera.worker)

    def test_rejects_cross_origin_and_bad_rotation(self):
        for headers, data, expected in [({'Origin': 'https://evil.example'}, {}, 403),
                                        ({}, {'rotation': 17}, 400),
                                        ({'Host': 'evil.example'}, {}, 403)]:
            with self.assertRaises(HTTPError) as exc:
                self.request('/api/start', data, **headers)
            self.assertEqual(exc.exception.code, expected)
        self.assertIsNone(self.camera.worker)

    def test_start_and_stop_through_http(self):
        with self.request('/api/start', {'rotation': 90}) as response:
            self.assertTrue(json.load(response)['active'])
        with self.assertRaises(HTTPError) as exc:
            self.request('/api/start', {})
        self.assertEqual(exc.exception.code, 409)
        with self.request('/api/stop', {}) as response:
            self.assertEqual(response.status, 200)
        self.camera.worker.join(1)
        self.assertFalse(self.camera.status()['active'])

    def test_posture_route_and_calibrate(self):
        with self.request('/api/posture') as response:
            state = json.load(response)
        self.assertFalse(state['calibrated'])
        self.assertIn('shoulder', state['labels'])
        with self.assertRaises(HTTPError) as exc:
            self.request('/api/calibrate', {})
        self.assertEqual(exc.exception.code, 400)
        self.request('/api/start', {}).close()
        with self.request('/api/calibrate', {}) as response:
            self.assertTrue(json.load(response)['posture']['calibrating'])


if __name__ == '__main__':
    unittest.main()
