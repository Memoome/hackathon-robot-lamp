import array,copy,importlib.util,json,pathlib,re,threading,time,wave
task=pathlib.Path(__file__).resolve().parents[1]
folder=task/'apps/LJWB03-Lamp-Demo'
spec=importlib.util.spec_from_file_location('lamp_demo',folder/'lamp_demo.py');lamp=importlib.util.module_from_spec(spec);spec.loader.exec_module(lamp)

class Fake(lamp.LampLink):
    def __init__(self):
        self.calls=[];self.cancel=threading.Event();self.ui_alive=time.monotonic()+100
        self.state={'pulse':[1500]*4,'active':[1,1,1,0],'moving':[0]*4,'base_spin':0}
        self.emit=lambda *args:None
    def exchange(self,command,*args,**kwargs):
        self.check();self.calls.append(command)
        assert len(command.split())<=8
        if command.startswith('arm_live glide '):
            values=list(map(int,command.split()[2:]));assert 10<=values[3]<=600
            self.state['pulse'][:3]=values[:3];self.state['moving'][:3]=[0,0,0]
        if command.startswith('arm_live engage '):
            words=command.split();i=lamp.PINS.index(int(words[2]));self.state['pulse'][i]=int(words[3]);self.state['active'][i]=1
        return b'emotion_state=0 emotion_id=-1 emotion_count=8'
    def wait_until(self,*args):self.check()
    def start_sound(self,index,volume):self.check();self.calls.append(('sound',index,volume))
    def finish_sound(self,index):self.check();self.calls.append(('done',index))
    def audio_ready(self):self.check()
    def hold_pause(self,seconds):self.check();self.calls.append(('pause',seconds))

starter=copy.deepcopy(lamp.DEFAULT);assert starter['duration']==6 and starter['max_speed']==60
f=Fake();f.state['active']=[0]*4;f.state['pulse']=[0]*4;f.prepare_pose(starter)
assert f.state['pulse'][:3]==starter['upright'] and sum('engage' in v for v in f.calls if isinstance(v,str))==3
f=Fake();f.state['active'][1]=0;f.prepare_pose(starter)
assert sum('engage' in v for v in f.calls if isinstance(v,str))==1
assert any(v.startswith('arm_live engage 10 ') for v in f.calls if isinstance(v,str))
for v in f.calls:
    if isinstance(v,str) and v.startswith('arm_live glide'):assert int(v.split()[-1])<=60
cfg=copy.deepcopy(lamp.DEFAULT);cfg.update(upright=[1400,1500,1600],slump=[1700,1300,1200])
for style,offset in [('Robot chirps',0),('Musical tones',2)]:
    for kind,d in [('slump',0),('recover',1)]:
        f=Fake();c=dict(cfg,style=style);f.perform(kind,c)
        assert ('sound',offset+d,90) in f.calls
        assert f.state['pulse'][:3]==c['slump' if kind=='slump' else 'upright']
        assert f.calls[-1]==('done',offset+d)
        assert not any(isinstance(v,str) and (' base ' in v or ' scene ' in v) for v in f.calls)
f=Fake();f.glide([1501]*3,12,cfg);assert f.calls[-1].endswith(' 10')
f=Fake();bad=copy.deepcopy(cfg);bad['slump']=[2600]*3
try:f.perform('slump',bad);raise AssertionError('Bad pose accepted')
except ValueError:assert not f.calls
f=Fake();f.cancel.set()
try:f.perform('slump',cfg);raise AssertionError('Cancellation ignored')
except lamp.Cancelled:assert not f.calls

for style,index in [('Robot chirps',4),('Musical tones',5)]:
    f=Fake();c=dict(cfg,style=style,water=[1600,1700,1400]);f.water(c)
    assert ('sound',index,90) in f.calls and ('done',index) in f.calls
    assert f.state['pulse'][:3]==c['upright']
    assert f.calls.index(('pause',1.2))>f.calls.index(('done',index))
    assert not any(isinstance(x,str) and (' base ' in x or ' scene ' in x) for x in f.calls)
class CancelWater(Fake):
    def hold_pause(self,seconds):self.cancel.set();self.check()
f=CancelWater();c=dict(cfg,water=[1600,1700,1400])
try:f.water(c);raise AssertionError('Water cancellation ignored')
except lamp.Cancelled:assert f.state['pulse'][:3]==c['water']  # No automatic return after Stop.
f=Fake()
try:f.water(dict(cfg,water=None));raise AssertionError('Untaught water pose accepted')
except ValueError:assert not f.calls
old=copy.deepcopy(cfg);old.pop('water',None);lamp.validate(old)

for style,index,ending in [('Robot chirps',6,1),('Musical tones',7,3)]:
    f=Fake();c=dict(cfg,style=style,stretch=[1600,1700,1400]);f.stretch(c)
    assert f.state['pulse'][:3]==c['upright']
    assert f.calls.index(('sound',index,90))<f.calls.index(('pause',2.0))<f.calls.index(('sound',ending,90))
    assert f.calls[-1]==('done',ending)
    assert not any(isinstance(x,str) and (' base ' in x or ' scene ' in x) for x in f.calls)
f=CancelWater();c=dict(cfg,stretch=[1600,1700,1400])
try:f.stretch(c);raise AssertionError('Stretch cancellation ignored')
except lamp.Cancelled:
    assert f.state['pulse'][:3]==c['stretch']
    assert ('sound',1,90) not in f.calls
for change in ({'stretch':None},{'stretch':cfg['upright']},{'stretch':[2600]*3}):
    f=Fake()
    try:f.stretch(dict(cfg,**change));raise AssertionError('Invalid stretch accepted')
    except ValueError:assert not f.calls
class OlderFirmware(Fake):
    def exchange(self,*args,**kwargs):
        super().exchange(*args,**kwargs)
        return b'emotion_state=0 emotion_id=-1 emotion_count=6'
f=OlderFirmware()
try:f.stretch(c);raise AssertionError('Old firmware accepted stretch')
except RuntimeError:assert not any(isinstance(x,tuple) or 'glide' in x for x in f.calls)
old.pop('stretch',None);lamp.validate(old)
for action in ('water','stretch'):
    f=Fake();f.state['pulse'][:3]=starter['upright'].copy();getattr(f,action)(starter)
    assert f.state['pulse'][:3]==starter['upright']
    for command in f.calls:
        if isinstance(command,str) and command.startswith('arm_live glide'):
            assert int(command.split()[-1])<=60

for name in ('robot_slump','robot_recover','music_slump','music_recover','robot_water','music_water','robot_stretch','music_stretch'):
    pcm=(folder/'sounds'/f'{name}.pcm').read_bytes()
    assert len(pcm)%320==0 and len(pcm)/32000<=2.4
    samples=array.array('h',pcm);assert 20000<max(abs(x) for x in samples)<32767
    assert all(abs(x)<32767 for x in samples)
    with wave.open(str(folder/'sounds'/f'{name}.wav'),'rb') as w:
        assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,16000)
        assert w.readframes(w.getnframes())==pcm
import tempfile
profile_temp=tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent)
original_here=lamp.HERE;lamp.HERE=pathlib.Path(profile_temp.name)
root=lamp.tk.Tk();root.withdraw();app=lamp.LampDemo(root);root.update()
lamp.HERE=original_here
assert not app.connected and app.cfg['upright']==lamp.STARTER_UPRIGHT and app.cfg['slump']==lamp.STARTER_SLUMP
assert str(app.slump_button['state'])=='disabled'
assert str(app.water_button['state'])=='disabled'
assert str(app.stretch_button['state'])=='disabled'
assert str(app.engage_buttons[0]['state'])=='disabled'
assert not app.link.s and app.link.jobs.empty()
assert set(app.pose_edits)==set(lamp.STARTER_POSES)
assert [int(v.get()) for v in app.pose_edits['water']]==lamp.STARTER_WATER
assert [int(v.get()) for v in app.pose_edits['stretch']]==lamp.STARTER_STRETCH
app.connected=True;app.power.set(True);app.cfg=c;app.state=Fake().state;app.sound_ready=True;app.sound_count=6;app.refresh()
assert str(app.stretch_button['state'])=='disabled'
app.sound_count=8;app.refresh();assert str(app.stretch_button['state'])=='normal'
root.geometry('880x880');root.deiconify();root.update()
for tab in app.tabs.tabs():
    app.tabs.select(tab);root.update_idletasks()
    frame=root.nametowidget(tab)
    assert frame.winfo_reqheight()<=frame.winfo_height(),(frame.winfo_reqheight(),frame.winfo_height())
root.destroy()
profile_temp.cleanup()
print('Passed: slump/recovery, water, stretch in both styles; Stop blocks return and ending cue; old firmware blocked before motion; bounds/commands/profile compatibility; eight audio assets; GUI tabs and idle/no commands.')
