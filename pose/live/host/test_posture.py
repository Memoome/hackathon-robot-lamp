import unittest
from posture import PostureMonitor, measurements

def frame():
    p=[None]*17
    p[0]=[160,60];p[5]=[120,120];p[6]=[200,120]
    p[11]=[130,200];p[12]=[190,200]
    return {'rotation':90,'width':320,'height':240,'people':[{'score':.8,'keypoints':p}]}

class PostureTests(unittest.TestCase):
    def calibrated(self):
        m=PostureMonitor();m.start_calibration()
        for t in (0,10,20):m.update(frame(),t)
        self.assertIsNotNone(m.baseline)
        return m

    def test_calibration_and_persistent_uneven_shoulders(self):
        m=self.calibrated();f=frame();f['people'][0]['keypoints'][5][1]=140
        for t in (30,45): self.assertEqual(m.update(f,t)[1]['shoulder'].split()[0], '观察中')
        self.assertEqual(m.update(f,60)[1]['shoulder'].split()[0], '持续提醒')
        self.assertEqual(m.update(frame(),70)[1]['shoulder'], '接近基线')

    def test_missing_shoulder_multipeople_and_edges_are_unknown(self):
        m=self.calibrated();f=frame();f['people'][0]['keypoints'][6]=None
        self.assertIn('无法判断',m.update(f,30)[0])
        f=frame();f['people'].append(f['people'][0]);self.assertIn('无法判断',m.update(f,40)[0])
        f=frame();f['people'][0]['keypoints'][5]=[2,100];self.assertIn('无法判断',m.update(f,50)[0])

    def test_missing_hip_and_nose_only_disables_relevant_measure(self):
        m=self.calibrated();f=frame();f['people'][0]['keypoints'][11]=None;f['people'][0]['keypoints'][0]=None
        _,d=m.update(f,30);self.assertEqual(d['torso'],'无法判断');self.assertEqual(d['head_drop'],'无法判断');self.assertEqual(d['shoulder'],'接近基线')

    def test_interruption_and_direction_reset(self):
        m=self.calibrated();f=frame();f['people'][0]['keypoints'][5][1]=140
        m.update(f,30);m.update(f,45);self.assertEqual(m.update(f,90)[1]['shoulder'],'观察中 0秒')
        f['rotation']=0;self.assertIn('重新校准',m.update(f,100)[0]);self.assertIsNone(m.baseline)

    def test_unstable_calibration_and_incomplete_baseline(self):
        m=PostureMonitor();m.start_calibration();m.update(frame(),0);m.update(frame(),10)
        f=frame();f['people'][0]['keypoints'][5][1]=140
        self.assertIn('变化过大',m.update(f,20)[0]);self.assertIsNone(m.baseline)
        m.start_calibration();f=frame();f['people'][0]['keypoints'][11]=None
        for t in (30,40,50):m.update(f,t)
        self.assertEqual(m.update(frame(),60)[1]['torso'],'无法判断')

    def test_head_drop_direction_and_torso(self):
        m=self.calibrated();f=frame();f['people'][0]['keypoints'][0][1]+=16
        f['people'][0]['keypoints'][11][0]-=20;f['people'][0]['keypoints'][12][0]-=20
        _,d=m.update(f,30);self.assertIn('观察中',d['head_drop']);self.assertIn('观察中',d['torso'])
        f['people'][0]['keypoints'][0][1]=40
        self.assertEqual(m.update(f,40)[1]['head_drop'],'接近基线')

if __name__=='__main__':unittest.main()
