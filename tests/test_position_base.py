import sys,pathlib,threading,copy,time,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'apps/LJWB03-Lamp-Demo'))
import visual_control as v
import wireless_link
wireless_link.settings=lambda: {}
row=dict(type='base_position',name='left',pulse=500,seconds=2)
assert v.base_angle(500)==0 and v.base_angle(2500)==180 and v.base_angle(500,True)==180
assert v.base_motion_duration(2500,row)>=2000/600
class Fake(v.VisualLink):
    def __init__(self):
        self.calls=[];self.cancel=threading.Event();self.ui_alive=time.monotonic()+100
        self.state=dict(pulse=[1200,1300,1400,1500],active=[1]*4,base_spin=0)
        self.emit=lambda *a:None
    def exchange(self,cmd,*args):
        self.calls.append(cmd)
        if cmd.startswith('arm_live jog'):
            _,_,pin,direction,speed,lo,hi,hold=cmd.split()
            assert pin=='15' and hold=='1' and 10<=int(speed)<=600
            self.state['pulse'][3]=int(hi) if int(direction) else int(lo)
        if cmd.startswith('arm_live engage'):self.state['pulse'][3]=int(cmd.split()[3])
    def wait_until(self,*args):pass
f=Fake();f.position_base(row);assert f.state['pulse']==[1200,1300,1400,500] and f.calls[-1]=='arm_live freeze'
assert not any(cmd.startswith('arm_live base ') for cmd in f.calls)
f=Fake();f.cancel.set()
try:f.position_base(row);raise AssertionError('cancel ignored')
except v.Cancelled:assert not f.calls
f=Fake();f.state['active'][3]=0
try:f.position_base(row);raise AssertionError('unarmed base moved')
except ValueError:assert f.calls==['arm_live status']
f=Fake();f.position_base(dict(row,pulse=1500),True);assert f.calls[-1]=='arm_live engage 15 1500 1'
root=v.tk.Tk();root.withdraw();app=v.App(root);app.auto_connect.set(False)
root.update();original=copy.deepcopy(app.p['calibration'])
project=v.fresh();project['routine']=[row];v.check_project(project)
for pulse in (499,2501):
    try:v.position_base_row(dict(row,pulse=pulse));raise AssertionError('bounds ignored')
    except ValueError:pass
clock=[100.];callbacks=[];old_after=root.after;old_clock=v.time.monotonic
root.after=lambda ms,fn=None,*args:callbacks.append((ms,fn,args));v.time.monotonic=lambda:clock[0]
try:
    app._preview([row,dict(row,pulse=2500),dict(row,pulse=1500)])
    while callbacks:
        ms,fn,args=callbacks.pop(0);clock[0]+=ms/1000
        if fn:fn(*args)
    assert not app.previewing and app.base_target.get()==1500 and app.link.jobs.empty()
    assert app.p['calibration']==original
finally:root.after=old_after;v.time.monotonic=old_clock;root.destroy()
print('PASS: SG90 position-only commands, bounds, selected-channel isolation, cancellation, engagement, animated routine preview without USB or calibration changes.')
