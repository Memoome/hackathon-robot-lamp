import json
import threading
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import live_pose as live

class Serial:
    def __init__(self,lines):self.lines=iter(lines);self.sent=[]
    def write(self,data):self.sent.append(data)
    def readline(self):return next(self.lines).encode()+b'\n'
    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True

def sample():
    data=bytes([128,16,128,235])*9600
    frame={'id':7,'rotation':90,'capture_ms':100}
    result=dict(id=7,rotation=90,width=320,height=240,inference_ms=7200.0,people=[dict(score=.8,box=[10,20,300,230],keypoints=[[100,100]]*17)])
    h=live.wire.fnv(data)
    lines=['LIVE_START '+json.dumps(frame),f'CAM_BEGIN 38400 120 160 UYVY {h:08x}']
    lines += [f'CAM_DATA {i} {data[i:i+96].hex()}' for i in range(0,len(data),96)]
    lines += [f'CAM_END 38400 {h:08x}','POSE_RESULT '+json.dumps(result),'I (9000) cam_test: CAM_DONE result=OK streaming=OFF']
    return lines,result

class Tests(unittest.TestCase):
    def test_sensor_id_error_is_preserved_for_viewer(self):
        s=Serial(['Camera sensor is not BF3901, PID=0x1d01',
                  'CAM_ERROR rc=-1 reason=ESP_FAIL'])
        with self.assertRaisesRegex(RuntimeError,'PID=0x1d01'):
            live.receive(s,threading.Event(),lambda *args:None)

    def test_session_captures_once_and_confirms_idle(self):
        lines,_=sample()
        s=Serial(['CAM_STATUS busy=0 error=0','LIVE_ROTATION 90']+lines+
                 ['CAM_STOP requested','CAM_STATUS busy=0 error=0'])
        with tempfile.TemporaryDirectory() as tmp, patch.object(live,'ROOT',Path(tmp)),patch.object(live.wire,'connect',return_value=s):
            results=live.session(threading.Event(),lambda *args:None,count=1)
            self.assertEqual(len(results),1)
            self.assertEqual(s.sent.count(b'cam_test capture\n'),1)
            self.assertIn(b'cam_test stop\n',s.sent)
            self.assertTrue(s.closed)
            self.assertIn('CAM_STATUS busy=0',next((Path(tmp)/'evidence').glob('*.log')).read_text())
    def test_busy_session_does_not_capture_or_stop_other_work(self):
        s=Serial(['CAM_STATUS busy=1 error=0'])
        with tempfile.TemporaryDirectory() as tmp, patch.object(live,'ROOT',Path(tmp)),patch.object(live.wire,'connect',return_value=s):
            with self.assertRaisesRegex(RuntimeError,'占用'):
                live.session(threading.Event(),lambda *args:None,count=1)
        self.assertEqual(s.sent,[b'cam_test status\n'])
    def test_status_waits_through_boot_and_preserves_log(self):
        s=Serial(['boot message','I LIVE_READY', 'I CAM_STATUS busy=0 error=0'])
        lines=[]
        self.assertIn('busy=0',live.wait_status(s,lines.append))
        self.assertEqual(lines[0],'boot message')
        self.assertIn(b'cam_test status\n',s.sent)
    def test_stop_confirmation_waits_for_idle(self):
        s=Serial(['CAM_STATUS busy=1 error=0','CAM_STOP requested','CAM_STATUS busy=0 error=0'])
        self.assertIn('busy=0',live.wait_status(s,lambda line:None,require_idle=True))
    def test_model_init_error_fails_immediately(self):
        with self.assertRaisesRegex(RuntimeError,'LIVE_ERROR'):
            live.wait_status(Serial(['LIVE_ERROR model_init']),lambda line:None)
    def test_capture_crash_is_not_a_transfer_timeout(self):
        with self.assertRaisesRegex(RuntimeError,'assert failed'):
            live.receive(Serial(['assert failed: camera']),threading.Event(),lambda *args:None)
    def test_complete_matching_frame(self):
        lines,_=sample();events=[]
        frame=live.receive(Serial(lines),threading.Event(),lambda k,v:events.append(k))
        self.assertEqual(events,['frame','result'])
        self.assertEqual((frame['w'],frame['h']),(160,120))
        self.assertEqual(len(live.overlay(frame)),160*120*3)
    def test_mismatched_result_not_displayed(self):
        lines,result=sample();result['id']=8;lines[-2]='POSE_RESULT '+json.dumps(result);events=[]
        with self.assertRaises(ValueError):live.receive(Serial(lines),threading.Event(),lambda k,v:events.append(k))
        self.assertEqual(events,['frame'])
    def test_missing_and_corrupt_image_rejected(self):
        lines,_=sample()
        for broken in (lines[:2]+lines[3:], lines[:-3]+['CAM_END 38400 00000000']):
            events=[]
            with self.assertRaises(ValueError):live.receive(Serial(broken),threading.Event(),lambda k,v:events.append(k))
            self.assertFalse(events)
    def test_stop_discards_pending_result(self):
        lines,_=sample();s=Serial(lines);stop=threading.Event();stop.set();events=[]
        self.assertIsNone(live.receive(s,stop,lambda k,v:events.append(k)))
        self.assertEqual(s.sent,[b'cam_test stop\n']);self.assertFalse(events)
    def test_missing_points_not_fabricated(self):
        frame={'id':1,'rotation':0}
        r=dict(id=1,rotation=0,width=240,height=320,inference_ms=1,people=[dict(score=.5,box=[0,0,239,319],keypoints=[None]*17)])
        self.assertEqual(live.validate_result(r,frame)['people'][0]['keypoints'],[None]*17)
    def test_detect_session_sends_detect_and_parses_boxes(self):
        lines,_=sample()
        detect=dict(id=7,rotation=90,width=320,height=240,inference_ms=118.2,people=[dict(score=.89,box=[160,0,318,239],center=[239,119])])
        lines[-2]='DETECT_RESULT '+json.dumps(detect)
        s=Serial(['CAM_STATUS busy=0 error=0','LIVE_ROTATION 90']+lines+['CAM_STATUS busy=0 error=0'])
        with tempfile.TemporaryDirectory() as tmp, patch.object(live,'ROOT',Path(tmp)),patch.object(live.wire,'connect',return_value=s):
            results=live.session(threading.Event(),lambda *args:None,count=1,mode='detect')
        self.assertEqual(s.sent.count(b'cam_test detect\n'),1)
        self.assertNotIn(b'cam_test capture\n',s.sent)
        self.assertEqual(results[0]['mode'],'detect')
        self.assertEqual(results[0]['people'][0]['center'],[239,119])
    def test_detect_mode_ignores_pose_result_and_rejects_keypoints(self):
        lines,_=sample()
        with self.assertRaises(RuntimeError):
            live.receive(Serial(lines),threading.Event(),lambda *a:None,mode='detect')
        frame={'id':1,'rotation':0}
        r=dict(id=1,rotation=0,width=240,height=320,inference_ms=1,people=[dict(score=.5,box=[0,0,239,319],keypoints=[None]*17)])
        with self.assertRaises(ValueError):live.validate_result(r,frame,'detect')
    def test_detect_overlay_draws_box_without_keypoints(self):
        lines,_=sample();lines[-2]='DETECT_RESULT '+json.dumps(dict(id=7,rotation=90,width=320,height=240,inference_ms=118.0,people=[dict(score=.9,box=[10,20,300,230],center=[155,125])]))
        frame=live.receive(Serial(lines),threading.Event(),lambda *a:None,mode='detect')
        self.assertNotEqual(live.overlay(frame),frame['rgb'])
    def stream_lines(self,stopped=True):
        import base64
        data=bytes(range(256))*20;h=live.wire.fnv(data)
        det=lambda seq,people=[]:'DET '+json.dumps(dict(seq=seq,t_ms=1000+seq*165,width=320,height=240,rotation=90,prep_ms=32.5,infer_ms=117.6,cycle_ms=165.0,people=people))
        head=dict(seq=2,t_ms=1330,w=240,h=320,bytes=len(data),fnv32=f'{h:08x}',quality=80,enc_ms=33.8,reason='preview')
        lines=[det(1),det(2,[dict(score=.9,box=[10,20,300,230],center=[155,125])]),'JPEG_BEGIN '+json.dumps(head)]
        lines+=[f'JPEG_DATA {i} {base64.b64encode(data[i:i+144]).decode()}' for i in range(0,len(data),144)]
        lines+=[f'JPEG_END 2 {len(data)} {h:08x}','POSE_RX {"seq":2,"state":"head_down","level":"watch","stale":0,"count":1,"latest_seq":3}',
                'STREAM_STATS {"valid":5,"bad":0,"dq_fail":0,"det":2,"preview":1,"preview_skipped":0,"psram_free":1}']
        return lines+(['I cam_test: CAM_DONE result=OK streaming=OFF'] if stopped else [])
    def test_stream_emits_detections_jpeg_pose_ack_and_stats(self):
        stop=threading.Event();events=[]
        def emit(kind,value):
            events.append((kind,value))
            if kind=='stats':stop.set()
        s=Serial(self.stream_lines())
        live.receive_stream(s,stop,emit,90)
        kinds=[k for k,_ in events]
        self.assertEqual(kinds,['det','det','jpeg','pose_rx','stats'])
        frame=events[2][1]
        self.assertEqual((frame['seq'],frame['bytes'],frame['rotation'],frame['reason']),(2,5120,90,'preview'))
        self.assertEqual(frame['data'],bytes(range(256))*20)
        self.assertEqual(frame['det']['people'][0]['center'],[155,125])
        self.assertEqual(events[3][1]['state'],'head_down')
        self.assertIn(b'cam_test stop\n',s.sent)
    def test_stream_emits_presence_and_board_calibration(self):
        st=dict(away=False,sedentary='watch',too_close='ok',standing=False)
        good=dict(seq=3,t_ms=1500,present=True,stable=True,sit_s=2400,states=st,calibrated=True,event='back',metrics=dict(area_ratio=1.1,rise=0.02),main=[1,2,3,4])
        lines=self.stream_lines();lines.insert(2,'PRESENCE '+json.dumps(good));lines.insert(3,'PRESENCE_CALIB {"ok":true,"seq":3,"area":18000,"top":60.0,"height":180.0}')
        stop=threading.Event();events=[]
        def emit(kind,value):
            events.append((kind,value))
            if kind=='stats':stop.set()
        live.receive_stream(Serial(lines),stop,emit,90)
        got=dict(events)
        self.assertEqual(got['presence']['states']['sedentary'],'watch')
        self.assertEqual(got['presence']['event'],'back')
        self.assertTrue(got['presence_calib']['ok'])
        for bad in (dict(good,sit_s=-1),dict(good,states=dict(st,too_close='close')),dict(good,event='gone'),dict(good,states=dict(st,away='no'))):
            with self.assertRaises(ValueError):live.validate_presence(bad)
    def test_stream_session_sends_auto_snap_before_start(self):
        s=Serial(['I CAM_STATUS busy=0 error=0','I LIVE_ROTATION 90','I cam_test: CAM_DONE result=OK streaming=OFF','I CAM_STATUS busy=0 error=0'])
        stop=threading.Event();stop.set()
        with tempfile.TemporaryDirectory() as tmp, patch.object(live,'ROOT',Path(tmp)),patch.object(live.wire,'connect',return_value=s):
            live.stream_session(stop,lambda *a:None,90,0,auto_snap=3)
        i=s.sent.index(b'cam_test auto_snap 3\n')
        self.assertLess(i,s.sent.index(b'cam_test stream_start\n'))
        with self.assertRaises(ValueError):live.stream_session(stop,lambda *a:None,90,0,auto_snap=601)
    def test_stream_writes_queued_commands_paced_and_logged(self):
        import queue
        q=queue.Queue();q.put(b'cam_test snap\n');q.put(b'cam_test pose {"seq":2}\n');stop=threading.Event();logged=[]
        class Slow(Serial):
            def readline(self):
                time.sleep(0.02);return super().readline()
        s=Slow(self.stream_lines())
        live.receive_stream(s,stop,lambda k,v:stop.set() if k=='stats' else None,90,diagnostic=logged.append,commands=q)
        self.assertEqual(s.sent[:2],[b'cam_test snap\n',b'cam_test pose {"seq":2}\n'])
        self.assertIn('HOST_TX cam_test snap',logged)
    def test_rejected_command_is_a_warning_not_a_failure(self):
        lines=self.stream_lines();lines.insert(1,'W (6625) cam_test: CAM_ERROR invalid_command argc=1 first=x')
        stop=threading.Event();events=[]
        def emit(kind,value):
            events.append(kind)
            if kind=='stats':stop.set()
        live.receive_stream(Serial(lines),stop,emit,90)
        self.assertIn('board_warning',events)
        with self.assertRaisesRegex(RuntimeError,'rc=263'):
            live.receive_stream(Serial(['E (1) cam_test: CAM_ERROR rc=263 reason=ESP_ERR_TIMEOUT']),threading.Event(),lambda *a:None,90)
    def test_stream_rejects_corrupt_jpeg(self):
        lines=self.stream_lines();i=lines.index(next(l for l in lines if l.startswith('JPEG_END')))
        lines[i]=lines[i].rsplit(' ',1)[0]+' 00000000'
        with self.assertRaisesRegex(ValueError,'checksum'):
            live.receive_stream(Serial(lines),threading.Event(),lambda *a:None,90)
    def test_stream_unexpected_end_and_silence_are_errors(self):
        with self.assertRaisesRegex(RuntimeError,'意外结束'):
            live.receive_stream(Serial(['I cam_test: CAM_DONE result=ERROR streaming=OFF']),threading.Event(),lambda *a:None,90)
        class Silent(Serial):
            def readline(self):return b''
        s=Silent([])
        with self.assertRaises(TimeoutError):
            live.receive_stream(s,threading.Event(),lambda *a:None,90,idle_timeout=0.05)
        self.assertIn(b'cam_test stop\n',s.sent)
    def test_stream_session_configures_preview_then_starts(self):
        s=Serial(['CAM_STATUS busy=0 error=0','LIVE_ROTATION 90']+self.stream_lines()+['CAM_STATUS busy=0 error=0'])
        stop=threading.Event()
        def emit(kind,value):
            if kind=='stats':stop.set()
        with tempfile.TemporaryDirectory() as tmp, patch.object(live,'ROOT',Path(tmp)),patch.object(live.wire,'connect',return_value=s):
            live.stream_session(stop,emit,preview_every=10)
        self.assertLess(s.sent.index(b'cam_test preview 10\n'),s.sent.index(b'cam_test stream_start\n'))
        with self.assertRaises(ValueError):live.stream_session(stop,emit,preview_every=-1)
    def test_rotation_preserves_geometry(self):
        raw=bytes([255,0,0,0,255,0])
        self.assertEqual(live.orient(raw,2,1,180),(bytes([0,255,0,255,0,0]),2,1))

if __name__=='__main__':unittest.main()
