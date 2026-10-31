import json
import threading
import unittest
from unittest.mock import patch
import live_pose as live

class Serial:
    def __init__(self,lines):self.lines=iter(lines);self.sent=[]
    def write(self,data):self.sent.append(data)
    def readline(self):return next(self.lines).encode()+b'\n'

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
    def test_rotation_preserves_geometry(self):
        raw=bytes([255,0,0,0,255,0])
        self.assertEqual(live.orient(raw,2,1,180),(bytes([0,255,0,255,0,0]),2,1))

if __name__=='__main__':unittest.main()
