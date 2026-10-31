import sys,pathlib,copy,threading,time,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'apps/LJWB03-Lamp-Demo'))
import visual_control as v
project=v.fresh();project['calibration']=[[[847,30],[1176,-3]],[[600,-150],[2365,-30]],[[1057,-20],[1500,-41]]]
v.ensure_full_pulse_range(project);original=copy.deepcopy(project);v.ensure_full_pulse_range(project)
assert project==original and project['config']['low']==[500]*3 and project['config']['high']==[2500]*3
for points in project['calibration']:
    for pulse in (500,501,847,1100,1500,2100,2499,2500):
        assert abs(v.interpolate(points,v.interpolate(points,pulse),True)-pulse)<1e-6
for pulse in (499,2501):
    try:v.check_pose([pulse]*3,project['config']);raise AssertionError('Out of bounds accepted')
    except ValueError:pass
for pts in ([[700,-40],[1300,20],[1900,80]],[[700,70],[1300,10],[1900,-50]]):
    for pulse in (700,900,1300,1600,1900):
        angle=v.interpolate(pts,pulse)
        assert abs(v.interpolate(pts,angle,True)-pulse)<1e-7
assert v.interpolate([[1000,0],[1500,50]],2000)==50
try:v.mapping([[500,0],[1500,20],[2500,10]]);raise AssertionError()
except ValueError:pass
class Fake(v.VisualLink):
    def __init__(self):
        self.calls=[];self.cancel=threading.Event();self.ui_alive=time.monotonic()+100
        self.state={'active':[1,1,1,0],'base_spin':0};self.emit=lambda *a:None
    def exchange(self,*args):self.check();self.calls.append(args)
    def glide(self,pulse,seconds,cfg):self.check();self.calls.append(('move',pulse))
    def start_sound(self,i,volume):self.check();self.calls.append(('sound',i))
    def finish_sound(self,i):self.check()
    def hold_pause(self,seconds):self.check();self.calls.append(('pause',seconds))
rows=[dict(name='a',pulse=[1000,1100,1200],seconds=3,pause=1,sound=4),dict(name='b',pulse=[1200,1300,1400],seconds=3,pause=0,sound=-1)]
f=Fake();f.perform('slump',(rows,v.DEFAULT,8));assert ('sound',4) in f.calls and f.calls[-2]==('move',rows[1]['pulse'])
f=Fake()
try:f.perform('slump',(rows,v.DEFAULT,4));raise AssertionError()
except ValueError:assert not f.calls
class Cancel(Fake):
    def hold_pause(self,seconds):self.cancel.set();self.check()
f=Cancel()
try:f.perform('slump',(rows,v.DEFAULT,8));raise AssertionError()
except v.Cancelled:assert ('move',rows[1]['pulse']) not in f.calls
root=v.tk.Tk();app=v.App(root);root.update()
assert app.link.jobs.empty() and app.link.s is None and not app.connected
assert len(app.coords(app.pulse()))==4
temp=tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent);v.FILE=pathlib.Path(temp.name)/'visual.json'
app.p=v.fresh();app.pulses[0].set(1000)
before=v.interpolate(app.p['calibration'][0],1000);slope=app.p['calibration'][0][-1][1]-app.p['calibration'][0][0][1]
app.reverse_joint()
assert abs(v.interpolate(app.p['calibration'][0],1000)-before)<1e-7
assert (app.p['calibration'][0][-1][1]-app.p['calibration'][0][0][1])*slope<0
app.joint.set('Middle');app.reverse_joint();v.check_project(app.p)
app.joint.set('Lift')
app.p=v.fresh();app.begin_match();app.match_angles[0]=20;app.finish_match()
assert abs(v.interpolate(app.p['calibration'][0],1000)-20)<1e-7
app.pulses[0].set(1400);app.begin_match();app.match_angles[0]=-20
try:app.send('slump',None);raise AssertionError('Movement not blocked during matching')
except ValueError:pass
app.finish_match()
assert app.p['calibrated'][0] and v.interpolate(app.p['calibration'][0],1400)==-20
assert app.link.jobs.empty() and app.link.s is None
v.check_project(__import__('json').loads(v.FILE.read_text()))
temp.cleanup()
temp=tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent);v.FILE=pathlib.Path(temp.name)/'visual.json'
app.p=v.fresh();v.upgrade_directions(app.p);app.joint.set('Lift');app.p['calibration'][0]=[[847,30],[1176,-3]]
app.range_edit.set(True);app.toggle_range();app.range_center.set(25);app.save_range()
pts=app.p['calibration'][0]
assert pts[0][0]==500 and pts[-1][0]==2500 and pts[0][1]-pts[-1][1]==180
for pulse in (500,1100,1500,2100,2500):assert abs(v.interpolate(pts,v.interpolate(pts,pulse),True)-pulse)<1e-7
app.pulses[0].set(1200);app.begin_match();app.match_angles[0]=20;app.finish_match()
assert abs(app.p['calibration'][0][-1][1]-app.p['calibration'][0][0][1])==180
assert app.link.jobs.empty() and not app.link.s
app.range_edit.set(True)
try:app.send('slump',None);raise AssertionError('Range editing allowed motion')
except ValueError:pass
app.range_edit.set(False);temp.cleanup()
temp=tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent);v.FILE=pathlib.Path(temp.name)/'visual.json'
app.p=v.fresh();v.upgrade_directions(app.p);app.joint.set('Lift');app.pulses[0].set(1000);app.p['calibration'][0]=[[847,30],[1176,-3]]
before=v.interpolate(app.p['calibration'][0],1000);app.restore_range()
assert abs(v.interpolate(app.p['calibration'][0],1000)-before)<1e-7
assert abs(app.p['calibration'][0][-1][1]-app.p['calibration'][0][0][1])==180
assert not app.range_edit.get() and '180.0' in app.range_summary.get()
temp.cleanup()
class BaseFake(Fake):
    def __init__(self):super().__init__();self.base_held=True
    def exchange(self,cmd,*args):
        self.calls.append(cmd)
        if len(self.calls)==2:self.base_held=False
    def wait_until(self,deadline):pass
f=BaseFake();base=dict(type='base',name='turn',direction=1,speed=5,neutral=1500,seconds=10,hold=True)
f.turn_base(base)
assert f.calls==['arm_live base 2 50 1500']*2+['arm_live base 0 0 1500']
f=BaseFake();f.cancel.set()
try:f.turn_base(base);raise AssertionError('Base cancellation ignored')
except v.Cancelled:assert f.calls[-1]=='arm_live base 0 0 1500'
project=v.fresh();project['routine']=[dict(base,hold=False,seconds=1)];v.check_project(project)
legacy=v.fresh();legacy.pop('direction_fix_20261030');legacy['calibration'][2]=[[500,-90],[2500,90]]
v.upgrade_directions(legacy);first=copy.deepcopy(legacy);v.upgrade_directions(legacy)
assert legacy==first and legacy['base_reverse'] and legacy['calibration'][2][0][1]>legacy['calibration'][2][-1][1]
assert legacy['calibration'][0][0][1]>legacy['calibration'][0][-1][1]
app.p=v.fresh()
for key,pulse in [('Rest',[1500,1500,1500]),('Slump',[1600,1550,1400]),('Water',[1550,1600,1450]),('Stretch',[1400,1450,1600])]:
    app.p['poses'][key]=pulse;app.roles[key].set(key)
for kind in ('Slump','Water','Stretch'):
    for style in ('Robot chirps','Musical tones'):
        app.action_style.set(style);rows=app.action_rows(kind)
        assert rows[0]['pulse']==rows[-1]['pulse']==app.p['poses']['Rest']
        assert any(row['pulse']==app.p['poses'][kind] for row in rows)
        assert any(row['sound']>=0 for row in rows) and len(rows)>=5
pose,duration=v.preview_motion([500,500,500],[2500,600,500],2,600,.5)
assert pose==[800,600,500] and abs(duration-2000/600)<1e-7
temp=tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent)
v.FILE=pathlib.Path(temp.name)/'current.json';v.PROFILES=pathlib.Path(temp.name)/'profiles'
v.upgrade_directions(app.p);v.ensure_full_pulse_range(app.p)
app.profile_name.set('Lamp Cardboard Prototype');saved_cal=copy.deepcopy(app.p['calibration']);saved_ranges=copy.deepcopy(app.p['full_ranges'])
app.save_profile();app.p['calibration'][0]=[[500,0],[2500,180]];app.load_profile()
assert app.p['calibration']==saved_cal and app.p['full_ranges']==saved_ranges and not app.live_enabled.get()
before_cal=copy.deepcopy(app.p['calibration']);before_poses=copy.deepcopy(app.p['poses']);old_sign=app.p.get('head_face_sign',1)
app.flip_face();assert app.p['head_face_sign']==-old_sign and app.p['calibration']==before_cal and app.p['poses']==before_poses
for canvas in (app.canvas,app.real_canvas):
    labels=[canvas.itemcget(item,'text') for item in canvas.find_all() if canvas.type(item)=='text']
    assert all(label in labels for label in ('J1 lift','J2 elbow','J3 head tilt','LAMP HEAD','FRONT','BASE · rotating pedestal'))
assert v.check_project(__import__('json').loads((v.PROFILES/'Lamp Cardboard Prototype.json').read_text()))
# Drive the screen animation with virtual time, with audio replaced by a recorder.
callbacks=[];clock=[100.0];sounds=[]
old_after=root.after;old_clock=v.time.monotonic;old_sound=v.winsound.PlaySound
root.after=lambda ms,fn=None,*args:callbacks.append((ms,fn,args))
v.time.monotonic=lambda:clock[0];v.winsound.PlaySound=lambda *args:sounds.append(args)
try:
    app._preview([dict(name='test',pulse=[1010,1020,1000],seconds=1,pause=.5,sound=1)])
    while callbacks:
        ms,fn,args=callbacks.pop(0);clock[0]+=ms/1000
        if fn:fn(*args)
    assert not app.previewing and app.preview_plan and app.pulse()==[1010,1020,1000]
    assert app.link.jobs.empty() and sounds
    for key,var in app.roles.items():var.set(key)
    for kind in ('Slump','Water','Stretch'):
        # Complete each one-click action in virtual time, without audio or USB.
        callbacks.clear();app.action_style.set('Robot chirps');rows=app.action_rows(kind)
        observed_before=copy.deepcopy(app.real_angles);app._preview(rows)
        iterations=0
        while callbacks:
            ms,fn,args=callbacks.pop(0);clock[0]+=ms/1000
            if fn:fn(*args)
            iterations+=1;assert iterations<10000
        assert not app.previewing and app.playback_progress.get()==100
        assert app.pulse()==rows[-1]['pulse'] and app.link.jobs.empty()
        assert app.real_angles==observed_before
    app._preview([dict(name='cancel',pulse=[1200,1200,1200],seconds=2,pause=0,sound=-1)])
    app.cancel_preview()
    assert not app.previewing and app.preview_plan is None and app.link.jobs.empty()
finally:
    root.after=old_after;v.time.monotonic=old_clock;v.winsound.PlaySound=old_sound
temp.cleanup()
attempts=[];old_port=v.board_port;old_send=app.send
v.board_port=lambda:'COM5';app.send=lambda *args:attempts.append(args)
app.connected=False;app.busy=False;app.closing=False;app.auto_connect.set(True);app.retry_at=0
app.retry_connection();app.retry_connection();assert attempts==[('connect',)]
app.auto_connect.set(False);app.retry_at=0;app.retry_connection();assert len(attempts)==1
app.events.put(('error','USB unplugged'));app.live_enabled.set(True);app.power.set(True);app.poll()
assert not app.connected and not app.live_enabled.get() and not app.power.get() and app.state is None
v.board_port=old_port;app.send=old_send
root.destroy()
class LiveFake(Fake):
    def __init__(self):
        super().__init__();self.live_held=True;self.live_target=([1100,1200,1300],400,time.monotonic());self.state['moving']=[0]*4
    def exchange(self,cmd,*args):
        self.calls.append(cmd)
        if cmd.startswith('arm_live glide'):self.live_held=False
    def wait_until(self,*args):pass
f=LiveFake();cfg=copy.deepcopy(v.DEFAULT);cfg['max_speed']=250;f.live_drag(cfg)
assert f.calls==['arm_live status','arm_live glide 1100 1200 1300 250','arm_live freeze']
f=LiveFake();f.live_target=([1100,1200,1300],400,time.monotonic()-1);f.live_drag(cfg)
assert f.calls==['arm_live status','arm_live freeze']
f=LiveFake();f.cancel.set()
try:f.live_drag(cfg);raise AssertionError('Live cancellation ignored')
except v.Cancelled:assert f.calls[-1]=='arm_live freeze'
print('PASS: base release/cancellation neutral, base routine compatibility, calibration reversal/matching, movement lock, persistence and idle GUI.')
