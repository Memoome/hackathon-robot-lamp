import copy,json,pathlib,sys,math,threading
folder=pathlib.Path(__file__).resolve().parents[1]/'apps/LJWB03-Lamp-Demo';sys.path.insert(0,str(folder))
import expressive_routines as e
import visual_control as v
p=json.loads((folder/'visual-lamp.json').read_text(encoding='utf-8'));before=copy.deepcopy(p)
home=p['poses'][p['roles']['Rest']];y0=e.geometry(p,home)[0][-1][1]
for kind in ('Slump','Water','Stretch'):
    for music in (False,True):
        rows=e.build_gesture(p,p['roles'],kind,music)
        project=copy.deepcopy(p);project['routine']=rows;v.check_project(project)
        assert rows[0]['pulse']==rows[-1]['pulse']==home
        total=0;previous=home
        for row in rows:
            total+=e.trajectory_duration(previous,row,600)+row['pause'];previous=row['pulse']
            assert e.geometry(p,row['pulse'])[0][-1][0]<0,'Lamp crossed to right side'
        assert 3<total<7,total
        if kind=='Slump':assert e.geometry(p,next(r['pulse'] for r in rows if 'Body gives in' in r['name']))[0][-1][1]>y0
        if kind=='Stretch':assert e.geometry(p,next(r['pulse'] for r in rows if 'Unfold slowly' in r['name']))[0][-1][1]<y0
        start=home
        for row in rows:
            for cap in (60,120,600):
                duration=e.trajectory_duration(start,row,cap);last=start
                assert e.sample_motion(start,row,0,cap)[0]==start
                assert e.sample_motion(start,row,duration,cap)[0]==row['pulse']
                for n in range(1,101):
                    current,_=e.sample_motion(start,row,n*duration/100,cap)
                    assert all(min(a,b)<=x<=max(a,b) for x,a,b in zip(current,start,row['pulse']))
                    assert max(abs(a-b) for a,b in zip(last,current))<=cap*duration/100+1.01
                    last=current
            start=row['pulse']
assert p==before,'Generator overwrote calibration or user checkpoints'
class Fake(v.VisualLink):
    def __init__(self):
        self.state=dict(pulse=home.copy()+[0],active=[1,1,1,0],base_spin=0);self.calls=[];self.cancel=threading.Event();self.ui_alive=100000;self.emit=lambda *a:None
    def exchange(self,cmd,*args):
        self.check();self.calls.append(cmd);assert len(cmd.split())<=8
        if cmd.startswith('arm_live glide '):self.state['pulse'][:3]=list(map(int,cmd.split()[2:5]))
    def wait_until(self,deadline):clock[0]=deadline;self.check()
    def glide(self,goal,seconds,cfg):self.check();self.state['pulse'][:3]=goal.copy()
    def hold_pause(self,seconds):clock[0]+=seconds;self.check()
    def start_sound(self,index,volume):self.check();self.calls.append(('sound',index))
    def finish_sound(self,index):self.check();self.calls.append(('finished',index))
clock=[0.];old=v.time.monotonic;v.time.monotonic=lambda:clock[0]
try:
    for kind in ('Slump','Water','Stretch'):
        f=Fake();rows=e.build_gesture(p,p['roles'],kind);f.perform('slump',(rows,p['config'],8))
        assert f.state['pulse'][:3]==home and any(isinstance(c,tuple) and c[0]=='sound' for c in f.calls)
        assert all('base' not in c for c in f.calls if isinstance(c,str))
finally:v.time.monotonic=old
print('PASS: all gestures/styles return home; model slump lowers and stretch rises; quintic no-overshoot/rate caps; same hardware sampler; sound ordering; calibration/checkpoints unchanged.')
