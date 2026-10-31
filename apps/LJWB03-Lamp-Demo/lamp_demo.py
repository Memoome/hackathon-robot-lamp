"""Lamp slump/recovery demo. No movement, recording or sound on launch/connect."""
import json,math,pathlib,queue,re,sys,threading,time,tkinter as tk
from tkinter import ttk,messagebox
import winsound
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'LJWB03-Arm-Controller'))
from greeting_demo import DemoLink,Cancelled
from arm_controller import board_port
import serial

PINS=(12,10,11)
NAMES=('Lift','Middle','Lamp head')
EMOTION=rb'emotion_state=(-?\d+) emotion_id=(-?\d+)'
STARTER_UPRIGHT=[1000,600,1500]  # Earlier Hello start; new head centred, not old plate endpoint.
STARTER_SLUMP=[1100,800,1550]    # Small exploratory bend; mechanical direction must be observed.
STARTER_WATER=[1050,750,1600]    # Estimated small forward/downward invitation, not bottle detection.
STARTER_STRETCH=[950,550,1400]   # Small opposite bend from slump; verify installed horn directions.
STARTER_POSES={'upright':STARTER_UPRIGHT,'slump':STARTER_SLUMP,'water':STARTER_WATER,'stretch':STARTER_STRETCH}
DEFAULT={'version':1,'pins':[12,10,11],'upright':STARTER_UPRIGHT.copy(),'slump':STARTER_SLUMP.copy(),'water':STARTER_WATER.copy(),'stretch':STARTER_STRETCH.copy(),
         'low':[500]*3,'high':[2500]*3,'start':STARTER_UPRIGHT.copy(),'duration':6.0,'max_speed':60,'volume':90,'style':'Robot chirps'}

def validate(cfg):
    if cfg.get('version')!=1 or cfg.get('pins')!=[12,10,11]:raise ValueError('Unsupported lamp profile.')
    for k in ('low','high','start'):
        if not isinstance(cfg.get(k),list) or len(cfg[k])!=3 or any(type(v)!=int for v in cfg[k]):raise ValueError('Invalid pulse settings.')
    for lo,hi,start in zip(cfg['low'],cfg['high'],cfg['start']):
        if not 500<=lo<hi<=2500 or not lo<=start<=hi:raise ValueError('Use pulse limits within500..2500, with starting values inside them.')
    for k in ('upright','slump','water','stretch'):
        p=cfg.get(k)
        if p is not None and (not isinstance(p,list) or len(p)!=3 or any(type(v)!=int or not lo<=v<=hi for v,lo,hi in zip(p,cfg['low'],cfg['high']))):raise ValueError('Saved '+k+' pose is outside these limits. Reteach it first.')
    if not isinstance(cfg.get('duration'),(int,float)) or not math.isfinite(cfg['duration']) or not 1<=cfg['duration']<=12:raise ValueError('Use a movement time of1..12seconds.')
    if type(cfg.get('volume'))!=int or not 0<=cfg['volume']<=100:raise ValueError('Volume must be0..100.')
    if cfg.get('style') not in ('Robot chirps','Musical tones'):raise ValueError('Select a sound style.')
    if type(cfg.get('max_speed',60))!=int or not 10<=cfg.get('max_speed',60)<=600:raise ValueError('Speed cap must be10..600µs/s.')
    return cfg

def phases(start,end):
    # Bend the two links first; the head follows with a short delay.
    return [list(end[:2])+[round(start[2]+.45*(end[2]-start[2]))],list(end)]

class LampLink(DemoLink):
    def check(self):
        if self.cancel.is_set():raise Cancelled('Stopped. Movement paused and sound cancelled.')
        if time.monotonic()-self.ui_alive>.8:raise Cancelled('Window stopped responding; movement cancelled.')
    def emotion_status(self):
        raw=self.exchange('audio_test status',EMOTION)
        m=re.search(EMOTION,raw)
        return int(m[1]),int(m[2])
    def hold_pause(self,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.check();self.exchange('arm_live ping');self.wait_until(min(end,time.monotonic()+.10))
    def audio_ready(self):
        deadline=time.monotonic()+4
        while True:
            self.check();name,busy,ready,_=self.audio_state()
            if name=='READY' and not busy and ready:return
            if time.monotonic()>deadline:raise RuntimeError('Speaker not ready. Stop and reconnect, or install the lamp sound update.')
            self.hold_pause(.1)
    def start_sound(self,index,volume):
        self.check();self.emotion_status();self.audio_ready()
        self.exchange(f'audio_test volume {volume}',rb'VOLUME requested=\d+ actual=\d+ hardware_max=31 rc=0')
        self.audio_ready();self.check()
        self.exchange(f'audio_test emotion {index}',rb'EMOTION_QUEUED id='+str(index).encode())
    def finish_sound(self,index):
        deadline=time.monotonic()+7
        while time.monotonic()<deadline:
            self.check();state,selected=self.emotion_status()
            if selected!=index:raise RuntimeError('Sound selection changed unexpectedly.')
            if state==-1:raise RuntimeError('Board reported sound cancelled or failed.')
            if state==2:return
            self.hold_pause(.1)
        raise RuntimeError('Speaker playback timed out.')
    def glide(self,goal,duration,cfg):
        self.check()
        initial=self.state['pulse'][:3]
        if self.state['active'][:3]!=[1,1,1] or self.state['base_spin']:raise RuntimeError('Engage the three lamp joints first; keep the base stopped.')
        if any(not lo<=v<=hi for pose in (initial,goal) for v,lo,hi in zip(pose,cfg['low'],cfg['high'])):raise ValueError('Current or requested pose is outside the saved limits.')
        distance=max(abs(a-b) for a,b in zip(initial,goal))
        if not distance:return
        speed=max(10,min(cfg.get('max_speed',60),math.ceil(distance/max(.2,duration))))
        deadline=time.monotonic()+distance/speed+4
        while True:
            self.check();self.exchange('arm_live glide '+' '.join(map(str,(*goal,speed))))
            if self.state['pulse'][:3]==goal and self.state['moving'][:3]==[0,0,0]:return
            if time.monotonic()>deadline:raise RuntimeError('Motion timed out; sequence stopped.')
            self.wait_until(time.monotonic()+.08)
    def perform(self,kind,cfg):
        validate(cfg)
        if cfg['upright'] is None or cfg['slump'] is None:raise ValueError('Teach and save both lamp poses first.')
        if cfg['upright']==cfg['slump']:raise ValueError('Upright and slump are identical; teach a different second pose.')
        self.exchange('arm_live status')
        goal=cfg['slump' if kind=='slump' else 'upright']
        if self.state['active'][:3]!=[1,1,1] or self.state['base_spin']:raise RuntimeError('Engage all three joints and stop the base before a routine.')
        # Validate before starting sound, so rejected motion never plays its cue.
        if any(not lo<=v<=hi for p in (self.state['pulse'][:3],goal) for v,lo,hi in zip(p,cfg['low'],cfg['high'])):raise ValueError('Pose outside limits.')
        index=(0 if cfg['style']=='Robot chirps' else 2)+(kind=='recover')
        targets=phases(self.state['pulse'][:3],goal)
        self.start_sound(index,cfg['volume'])
        self.emit('phase','Drooping gently…' if kind=='slump' else 'Straightening up…')
        self.glide(targets[0],cfg['duration']*.75,cfg)
        self.glide(targets[1],cfg['duration']*.25,cfg)
        self.finish_sound(index)
        self.emit('finished','Slumped pose holding. Press Recover when ready.' if kind=='slump' else 'Upright pose holding. Ready for another interaction.')
    def prepare_pose(self,cfg):
        self.check();validate(cfg);self.exchange('arm_live status')
        if self.state['base_spin']:raise RuntimeError('Stop the base before setting a starting pose.')
        goal=cfg['upright']
        if goal is None:raise ValueError('Load the starter routine or save an upright pose first.')
        # Unknown shafts cannot be ramped from a measured position. Only engage
        # inactive joints; already active joints keep their targets until glide.
        for i in range(3):
            self.check()
            if not self.state['active'][i]:self.exchange(f'arm_live engage {PINS[i]} {goal[i]} 1')
        self.glide(goal,cfg['duration'],cfg)
        self.emit('finished','Starting pose set. Choose Slump, Water break or Stretch. All return/recovery movements use this upright pose.')
    def water(self,cfg):
        validate(cfg)
        rest=cfg['upright'];target=cfg.get('water')
        if rest is None or target is None:raise ValueError('Teach upright and the water-bottle pose first.')
        if rest==target:raise ValueError('The water pose must differ from upright.')
        self.exchange('arm_live status')
        if self.state['active'][:3]!=[1,1,1] or self.state['base_spin']:raise RuntimeError('Engage all three joints and keep the base stopped.')
        if any(not lo<=v<=hi for p in (self.state['pulse'][:3],rest,target) for v,lo,hi in zip(p,cfg['low'],cfg['high'])):raise ValueError('Pose outside limits.')
        # Check firmware capability before any movement or sound.
        raw=self.exchange('audio_test status',EMOTION)
        count=re.search(rb'emotion_count=(\d+)',raw)
        if not count or int(count[1])<6:raise RuntimeError('Install the water-sound firmware update before running this routine.')
        self.audio_ready()
        self.emit('phase','Returning upright before the water invitation…')
        self.glide(rest,cfg['duration'],cfg)
        self.emit('phase','Looking toward the saved bottle spot…')
        for goal,portion in zip(phases(rest,target),(.75,.25)):self.glide(goal,cfg['duration']*portion,cfg)
        index=4 if cfg['style']=='Robot chirps' else 5
        self.start_sound(index,cfg['volume']);self.finish_sound(index)
        self.emit('phase','Water break? Holding the invitation…');self.hold_pause(1.2)
        self.check();self.emit('phase','Returning gently to upright…')
        self.glide(rest,cfg['duration'],cfg)
        self.emit('finished','Water invitation complete. Upright pose holding; bottle stays in its marked spot.')
    def stretch(self,cfg):
        validate(cfg)
        rest=cfg['upright'];target=cfg.get('stretch')
        if rest is None or target is None:raise ValueError('Teach upright and a comfortable stretch pose first.')
        if rest==target:raise ValueError('Stretch must differ from upright. Use a small comfortable lift, not the mechanical limit.')
        self.exchange('arm_live status')
        if self.state['active'][:3]!=[1,1,1] or self.state['base_spin']:raise RuntimeError('Engage all three joints and keep the base stopped.')
        if any(not lo<=v<=hi for p in (self.state['pulse'][:3],rest,target) for v,lo,hi in zip(p,cfg['low'],cfg['high'])):raise ValueError('Pose outside limits.')
        raw=self.exchange('audio_test status',EMOTION)
        count=re.search(rb'emotion_count=(\d+)',raw)
        if not count or int(count[1])<8:raise RuntimeError('Install the stretch-sound update before running this routine.')
        self.audio_ready()
        self.emit('phase','Settling upright before the stretch…')
        duration=max(3.0,cfg['duration'])
        self.glide(rest,duration,cfg)
        index=6 if cfg['style']=='Robot chirps' else 7
        self.start_sound(index,cfg['volume'])
        self.emit('phase','Stretch with me! Rising gently; the head follows…')
        for goal,portion in zip(phases(rest,target),(.75,.25)):self.glide(goal,duration*portion,cfg)
        self.finish_sound(index)
        self.emit('phase','Holding the comfortable stretch for two seconds…')
        self.hold_pause(2.0);self.check()
        self.emit('phase','Relaxing back upright…')
        self.glide(rest,duration,cfg)
        self.check()
        ending=1 if cfg['style']=='Robot chirps' else 3
        self.start_sound(ending,cfg['volume']);self.finish_sound(ending)
        self.emit('finished','Stretch complete. Upright pose holding. No camera detection was used.')
    def worker(self):
        while True:
            kind=None
            try:
                try:kind,data=self.jobs.get(timeout=.2)
                except queue.Empty:
                    if self.s and time.monotonic()-self.ui_alive<.8:self.exchange('arm_live ping')
                    continue
                if kind=='connect':
                    if self.s:self.s.close()
                    self.session=None;p=board_port();self.s=serial.Serial(port=None,baudrate=115200,timeout=.025,rtscts=False,dsrdtr=False)
                    self.s.dtr=False;self.s.rts=False;self.s.port=p;self.s.open()
                    self.exchange('arm_live status');self.session=self.state['session']
                    if any(self.state['active']):raise RuntimeError('Earlier outputs are active. Support/release the lamp using the earlier controller first.')
                    raw=self.exchange('audio_test status',rb'STATUS mode=OFFLINE_PCM')
                    count=re.search(rb'emotion_count=(\d+)',raw)
                    self.emit('connected',(p,int(count[1]) if count else 4 if re.search(EMOTION,raw) else 0))
                elif kind in ('stop','off','close'):
                    self.stop_hardware(kind!='stop');self.emit('finished','Stopped; current targets held.' if kind=='stop' else 'Outputs released. Support the lamp.')
                    if kind=='close':
                        if self.s:self.s.close()
                        self.emit('closed',None);return
                else:
                    self.check()
                    if kind=='prepare':
                        self.prepare_pose(data)
                    elif kind=='engage':
                        index,pulse,cfg=data;validate(cfg)
                        if index not in range(3) or not cfg['low'][index]<=pulse<=cfg['high'][index]:raise ValueError('Starting pulse outside limits.')
                        self.exchange(f'arm_live engage {PINS[index]} {pulse} 1');self.emit('finished',NAMES[index]+' engaged. Position is a command, not measured feedback.')
                    elif kind=='jog':
                        index,delta,cfg=data;validate(cfg);self.exchange('arm_live status')
                        goal=self.state['pulse'][:3].copy();goal[index]=max(cfg['low'][index],min(cfg['high'][index],goal[index]+delta))
                        self.glide(goal,max(abs(delta)/150,.2),cfg);self.emit('finished','Adjusted. Save the pose when it looks right.')
                    elif kind in ('slump','recover'):self.perform(kind,data)
                    elif kind=='water':self.water(data)
                    elif kind=='stretch':self.stretch(data)
                    elif kind=='sound':
                        index,volume=data;self.start_sound(index,volume);self.finish_sound(index);self.emit('finished','Sound finished. Listen to confirm quality.')
            except Cancelled as exc:
                try:self.stop_hardware(False)
                except Exception:pass
                self.emit('finished',str(exc))
            except Exception as exc:
                if self.s and kind!='connect':
                    try:self.stop_hardware(False)
                    except Exception:pass
                if self.s:self.s.close()
                self.s=None;self.session=None;self.state=None;self.emit('error',str(exc))
                if kind=='close':self.emit('closed',None);return
    def submit(self,kind,data=None):
        if kind in ('prepare','engage','jog','slump','recover','water','stretch','sound'):self.cancel.clear()
        super().submit(kind,data)

class LampDemo:
    def __init__(self,root):
        self.root=root;self.events=queue.Queue();self.connected=False;self.busy=False;self.closing=False;self.state=None;self.sound_ready=False;self.sound_count=0
        self.cfg=json.loads(json.dumps(DEFAULT));self.profile_warning=''
        try:self.cfg=validate(json.loads((HERE/'lamp-poses.json').read_text()))
        except FileNotFoundError:pass
        except Exception as exc:self.profile_warning='Saved profile ignored: '+str(exc)
        self.link=LampLink(lambda *e:self.events.put(e))
        root.title('Lamp · Slump, water and stretch');root.geometry('880x880');root.minsize(820,850);root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam');style.configure('TButton',font=('Segoe UI',10),padding=(10,7));style.configure('TLabel',font=('Segoe UI',10))
        box=ttk.Frame(root,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='A little companion. A little encouragement.',font=('Segoe UI',20,'bold')).pack(anchor='w')
        ttk.Label(box,text='Slow starter routine ready · lift12, middle10, head11 · base stays still. Adjust the preset as needed.',wraplength=790).pack(anchor='w',pady=7)
        row=ttk.Frame(box);row.pack(fill='x');self.connection=tk.StringVar(value='Not connected · laptop sound previews work now')
        ttk.Label(row,textvariable=self.connection).pack(side='left');self.connect_button=ttk.Button(row,text='Connect board',command=lambda:self.send('connect'));self.connect_button.pack(side='right')
        self.power=tk.BooleanVar();ttk.Checkbutton(box,text='External servo power and common ground checked; lamp supported and clear',variable=self.power,command=self.guard).pack(anchor='w',pady=10)
        self.tabs=ttk.Notebook(box);self.tabs.pack(fill='both',expand=True)
        perform=ttk.Frame(self.tabs,padding=15);teach=ttk.Frame(self.tabs,padding=15)
        self.tabs.add(perform,text='Play the interaction');self.tabs.add(teach,text='Teach lamp poses')
        row=ttk.Frame(perform);row.pack(fill='x',pady=8)
        self.style=tk.StringVar(value=self.cfg['style']);ttk.Label(row,text='Sound style').pack(side='left')
        ttk.Combobox(row,textvariable=self.style,values=['Robot chirps','Musical tones'],state='readonly',width=20).pack(side='left',padx=12)
        self.duration=tk.StringVar(value=str(self.cfg['duration']));ttk.Label(row,text='Movement seconds').pack(side='left');ttk.Spinbox(row,from_=1,to=12,increment=.5,textvariable=self.duration,width=6).pack(side='left',padx=8)
        self.volume=tk.StringVar(value=str(self.cfg['volume']));row=ttk.Frame(perform);row.pack(fill='x',pady=8)
        ttk.Label(row,text='Robot volume %').pack(side='left');ttk.Spinbox(row,from_=0,to=100,textvariable=self.volume,width=6).pack(side='left',padx=8)
        self.prepare_button=ttk.Button(perform,text='1. Set starting pose',command=self.prepare);self.prepare_button.pack(fill='x',pady=(12,6))
        self.slump_button=ttk.Button(perform,text='2. Slump + sound',command=lambda:self.action('slump'));self.slump_button.pack(fill='x',pady=6)
        self.recover_button=ttk.Button(perform,text='Recover + sound',command=lambda:self.action('recover'));self.recover_button.pack(fill='x',pady=6)
        self.water_button=ttk.Button(perform,text='Water break · gesture + sound + return',command=lambda:self.action('water'));self.water_button.pack(fill='x',pady=6)
        self.stretch_button=ttk.Button(perform,text='Stretch with me · rise + hold + relax',command=lambda:self.action('stretch'));self.stretch_button.pack(fill='x',pady=6)
        adjust=ttk.Frame(self.tabs,padding=16);self.tabs.add(adjust,text='Adjust routine')
        ttk.Label(adjust,text='Editable starter poses: upright, slump, water invitation and stretch.\nDirections are estimates from earlier trials, not measured lamp calibration.\nSave edits before running. No movement happens when saving.',wraplength=730).grid(row=0,column=0,columnspan=4,sticky='w',pady=12)
        self.pose_edits={}
        for col,name in enumerate(('Pose','Lift µs','Middle µs','Head µs')):ttk.Label(adjust,text=name).grid(row=1,column=col,padx=12,pady=6)
        for row,key in enumerate(STARTER_POSES,2):
            ttk.Label(adjust,text=key.title()).grid(row=row,column=0,padx=12,pady=8)
            self.pose_edits[key]=[]
            for col,value in enumerate(self.cfg.get(key) or ('','',''),1):
                v=tk.StringVar(value=str(value));self.pose_edits[key].append(v);ttk.Entry(adjust,textvariable=v,width=10).grid(row=row,column=col,padx=12)
        ttk.Button(adjust,text='Save routine edits',command=self.save_routine).grid(row=6,column=0,columnspan=2,sticky='ew',pady=18)
        ttk.Button(adjust,text='Load all slow starter poses',command=self.load_starter).grid(row=6,column=2,columnspan=2,sticky='ew',pady=18)
        ttk.Label(adjust,text='Default movement time: six seconds; speed capped at60µs/s.\nWater: gesture, invitation sound, pause, return. Stretch: rise, hold, relax, happy cue.\nFirst engagement can jump. Base stays still. STOP if a bend goes the wrong way.',wraplength=730).grid(row=7,column=0,columnspan=4,sticky='w',pady=12)
        sounds=ttk.Frame(self.tabs,padding=16);self.tabs.add(sounds,text='Sound previews')
        ttk.Label(sounds,text='Choose the sound style in Play the interaction. Laptop previews need no board.').pack(anchor='w',pady=10)
        row=ttk.Frame(sounds);row.pack(fill='x',pady=10)
        self.sound_buttons=[]
        for kind,label in [('slump','Slump sound on robot'),('recover','Recovery sound on robot')]:
            b=ttk.Button(row,text=label,command=lambda k=kind:self.robot_sound(k));b.pack(side='left',expand=True,fill='x',padx=3);self.sound_buttons.append(b)
        ttk.Button(sounds,text='Preview selected pair on laptop',command=self.preview).pack(fill='x',pady=5)
        row=ttk.Frame(sounds);row.pack(fill='x',pady=5)
        ttk.Button(row,text='Preview water sound on laptop',command=self.preview_water).pack(side='left',expand=True,fill='x',padx=3)
        self.water_sound_button=ttk.Button(row,text='Water sound on robot',command=self.water_sound);self.water_sound_button.pack(side='left',expand=True,fill='x',padx=3)
        row=ttk.Frame(sounds);row.pack(fill='x',pady=5)
        ttk.Button(row,text='Preview stretch + happy ending on laptop',command=self.preview_stretch).pack(side='left',expand=True,fill='x',padx=3)
        self.stretch_sound_button=ttk.Button(row,text='Stretch cue on robot',command=self.stretch_sound);self.stretch_sound_button.pack(side='left',expand=True,fill='x',padx=3)
        self.pose_text=tk.StringVar();ttk.Label(perform,textvariable=self.pose_text,wraplength=740).pack(anchor='w',pady=12)
        ttk.Label(perform,text='Slump/recovery hold their pose; water/stretch return upright. Stop cancels the rest.\nRelease switches off servo signals; support the lamp first.',wraplength=740).pack(anchor='w')
        ttk.Label(teach,text='1. Set safe limits and starting pulses. Engage each joint with the lamp supported.\n2. Save upright and the poses for the actions you want: slump, bottle, stretch.\nSaved positions are pulse commands, not measured angles; base stays still.',wraplength=740).grid(row=0,column=0,columnspan=7,sticky='w',pady=(0,12))
        self.low=[];self.high=[];self.starts=[];self.readouts=[];self.engage_buttons=[];self.jog_buttons=[]
        for col,text in enumerate(('Joint','Min µs','Max µs','Start µs','Engage','−','+')):ttk.Label(teach,text=text).grid(row=1,column=col,padx=4,pady=5)
        for i,name in enumerate(NAMES):
            value=tk.StringVar(value='Unknown');self.readouts.append(value)
            ttk.Label(teach,text=name+' · GPIO'+str(PINS[i])).grid(row=2+i*2,column=0,sticky='w',padx=4)
            for col,key,store in [(1,'low',self.low),(2,'high',self.high),(3,'start',self.starts)]:
                v=tk.StringVar(value=str(self.cfg[key][i]));store.append(v);ttk.Entry(teach,textvariable=v,width=8).grid(row=2+i*2,column=col,padx=4)
            b=ttk.Button(teach,text='Engage',command=lambda j=i:self.engage(j));b.grid(row=2+i*2,column=4,padx=4);self.engage_buttons.append(b)
            for col,direction in [(5,-1),(6,1)]:
                b=ttk.Button(teach,text='−' if direction<0 else '+',width=3,command=lambda j=i,d=direction:self.jog(j,d));b.grid(row=2+i*2,column=col,padx=2);self.jog_buttons.append(b)
            ttk.Label(teach,textvariable=value).grid(row=3+i*2,column=0,columnspan=7,sticky='w',padx=4,pady=(1,12))
        self.step=tk.StringVar(value='10');ttk.Label(teach,text='Adjustment µs (1..2000)').grid(row=8,column=0,columnspan=2,sticky='w');ttk.Spinbox(teach,from_=1,to=2000,textvariable=self.step,width=8).grid(row=8,column=2)
        self.save_upright=ttk.Button(teach,text='Save current as upright',command=lambda:self.save_pose('upright'));self.save_upright.grid(row=9,column=0,columnspan=3,sticky='ew',pady=14)
        self.save_slump=ttk.Button(teach,text='Save current as slump',command=lambda:self.save_pose('slump'));self.save_slump.grid(row=9,column=3,columnspan=4,sticky='ew',pady=14)
        self.save_water=ttk.Button(teach,text='Save current as water-bottle pose',command=lambda:self.save_pose('water'));self.save_water.grid(row=10,column=0,columnspan=7,sticky='ew',pady=(0,10))
        self.save_stretch=ttk.Button(teach,text='Save current as comfortable stretch',command=lambda:self.save_pose('stretch'));self.save_stretch.grid(row=11,column=0,columnspan=7,sticky='ew',pady=(0,10))
        ttk.Button(teach,text='Save settings',command=self.save_settings).grid(row=12,column=0,columnspan=3,sticky='ew')
        ttk.Button(teach,text='Clear saved poses',command=self.clear_poses).grid(row=12,column=3,columnspan=4,sticky='ew')
        ttk.Label(teach,text='500..2500µs are electrical bounds from earlier trials.\nThe new linkage may need narrower limits. Do not force mechanical stops.',wraplength=730).grid(row=13,column=0,columnspan=7,sticky='w',pady=12)
        row=ttk.Frame(box);row.pack(fill='x',pady=12)
        self.stop_button=ttk.Button(row,text='STOP movement + sound',command=self.stop);self.stop_button.pack(side='left',fill='x',expand=True,padx=(0,5))
        self.off_button=ttk.Button(row,text='Release outputs',command=self.release);self.off_button.pack(side='left',fill='x',expand=True,padx=(5,0))
        self.status=tk.StringVar(value=self.profile_warning or 'Starter poses ready. Connect, check power, Set starting pose, then choose an action.')
        ttk.Label(box,textvariable=self.status,wraplength=790).pack(anchor='w')
        self.refresh();root.after(50,self.poll)
    def config(self):
        cfg=dict(self.cfg,low=[int(v.get()) for v in self.low],high=[int(v.get()) for v in self.high],start=[int(v.get()) for v in self.starts],duration=float(self.duration.get()),volume=int(self.volume.get()),style=self.style.get())
        return validate(cfg)
    def refresh(self):
        ready=self.connected and not self.busy and not self.closing
        armed=ready and self.power.get()
        all_on=bool(self.state and self.state['active'][:3]==[1,1,1] and not self.state['base_spin'])
        self.connect_button.configure(state='normal' if not self.busy and not self.connected else 'disabled')
        self.prepare_button.configure(state='normal' if armed and self.cfg.get('upright') else 'disabled')
        for b in self.engage_buttons:b.configure(state='normal' if armed else 'disabled')
        for b in self.jog_buttons+[self.save_upright,self.save_slump,self.save_water,self.save_stretch]:b.configure(state='normal' if armed and all_on else 'disabled')
        for b in [self.slump_button,self.recover_button]:b.configure(state='normal' if armed and all_on and self.sound_ready and self.cfg['upright'] and self.cfg['slump'] else 'disabled')
        for b in self.sound_buttons:b.configure(state='normal' if ready and self.sound_ready else 'disabled')
        self.water_button.configure(state='normal' if armed and all_on and self.sound_count>=6 and self.cfg['upright'] and self.cfg.get('water') else 'disabled')
        self.stretch_button.configure(state='normal' if armed and all_on and self.sound_count>=8 and self.cfg['upright'] and self.cfg.get('stretch') else 'disabled')
        self.stretch_sound_button.configure(state='normal' if ready and self.sound_count>=8 else 'disabled')
        self.water_sound_button.configure(state='normal' if ready and self.sound_count>=6 else 'disabled')
        for b in [self.stop_button,self.off_button]:b.configure(state='normal' if self.connected and not self.closing else 'disabled')
        self.pose_text.set('Upright: '+str(self.cfg['upright'] or 'not taught')+'\nSlump: '+str(self.cfg['slump'] or 'not taught')+'\nWater bottle: '+str(self.cfg.get('water') or 'not taught')+'\nStretch: '+str(self.cfg.get('stretch') or 'not taught'))
        for i,v in enumerate(self.readouts):v.set('Last command: '+str(self.state['pulse'][i])+'µs · '+('holding' if self.state['active'][i] else 'released / position unknown') if self.state else 'Position unknown')
    def send(self,kind,data=None):
        if self.busy or self.closing:return
        self.busy=True;self.refresh();self.link.submit(kind,data)
    def guard(self):
        if not self.power.get() and self.busy:self.stop()
        self.refresh()
    def engage(self,i):
        try:
            cfg=self.config();pulse=cfg['start'][i]
            if not messagebox.askokcancel('Support the lamp',f'Engage {NAMES[i]} at{pulse}µs? Its physical position is unknown and first engagement can jump. Support/unload the mechanism and check clearance.',parent=self.root):return
            self.send('engage',(i,pulse,cfg))
        except Exception as exc:messagebox.showerror('Settings',str(exc),parent=self.root)
    def prepare(self):
        try:
            cfg=self.config()
            if not messagebox.askokcancel('Set starting pose',f"Set lift / middle / head to {cfg['upright']}µs?\nSupport the lamp and check clearance. First engagement may jump; later movement is slow.",parent=self.root):return
            self.send('prepare',cfg)
        except Exception as exc:messagebox.showerror('Settings',str(exc),parent=self.root)
    def save_routine(self):
        if self.busy:return
        try:
            cfg=self.config()
            for key in STARTER_POSES:
                values=[v.get().strip() for v in self.pose_edits[key]]
                cfg[key]=None if not any(values) else [int(v) for v in values]
            if cfg['upright'] is None:raise ValueError('Enter an upright pose before saving the routine.')
            cfg['start']=cfg['upright'].copy();validate(cfg)
            tmp=HERE/'lamp-poses.tmp';tmp.write_text(json.dumps(cfg,indent=2));tmp.replace(HERE/'lamp-poses.json');self.cfg=cfg
            for v,value in zip(self.starts,cfg['start']):v.set(str(value))
            self.status.set('Routine saved. No movement sent.');self.refresh()
        except Exception as exc:messagebox.showerror('Routine',str(exc),parent=self.root)
    def load_starter(self):
        if self.busy:return
        for key,values in STARTER_POSES.items():
            for v,value in zip(self.pose_edits[key],values):v.set(str(value))
        self.cfg['max_speed']=60;self.duration.set('6.0');self.save_routine()
    def jog(self,i,d):
        try:
            step=int(self.step.get())
            if not 1<=step<=2000:raise ValueError('Adjustment must be1..2000µs.')
            self.send('jog',(i,d*step,self.config()))
        except Exception as exc:messagebox.showerror('Settings',str(exc),parent=self.root)
    def save_settings(self):
        try:
            cfg=self.config();tmp=HERE/'lamp-poses.tmp';tmp.write_text(json.dumps(cfg,indent=2));tmp.replace(HERE/'lamp-poses.json');self.cfg=cfg;self.status.set('Lamp settings saved. No movement sent.');self.refresh()
            for key,editors in self.pose_edits.items():
                for editor,value in zip(editors,cfg.get(key) or ('','','')):editor.set(str(value))
        except Exception as exc:messagebox.showerror('Save settings',str(exc),parent=self.root)
    def save_pose(self,kind):
        if not self.state or self.busy:return
        old=self.cfg.get(kind);self.cfg[kind]=self.state['pulse'][:3].copy()
        try:validate(self.config())
        except Exception as exc:self.cfg[kind]=old;messagebox.showerror('Save pose',str(exc),parent=self.root);return
        self.save_settings()
    def clear_poses(self):
        if self.busy:return
        if messagebox.askokcancel('Teach again','Forget all saved poses so you can teach a new structure? No movement will be sent.',parent=self.root):
            self.cfg['upright']=None;self.cfg['slump']=None;self.cfg['water']=None;self.cfg['stretch']=None;self.save_settings()
    def action(self,kind):
        try:self.send(kind,self.config())
        except Exception as exc:messagebox.showerror('Settings',str(exc),parent=self.root)
    def robot_sound(self,kind):
        try:
            cfg=self.config();index=(0 if cfg['style']=='Robot chirps' else 2)+(kind=='recover');self.send('sound',(index,cfg['volume']))
        except Exception as exc:messagebox.showerror('Settings',str(exc),parent=self.root)
    def preview(self):
        style='robot' if self.style.get()=='Robot chirps' else 'music'
        winsound.PlaySound(str(HERE/'sounds'/f'{style}_preview.wav'),winsound.SND_FILENAME|winsound.SND_ASYNC)
        self.status.set('Laptop preview: slump, pause, recovery. The lamp is not moving.')
    def preview_water(self):
        style='robot' if self.style.get()=='Robot chirps' else 'music'
        winsound.PlaySound(str(HERE/'sounds'/f'{style}_water.wav'),winsound.SND_FILENAME|winsound.SND_ASYNC)
        self.status.set('Laptop preview: a friendly water-break invitation. No movement.')
    def preview_stretch(self):
        style='robot' if self.style.get()=='Robot chirps' else 'music'
        winsound.PlaySound(str(HERE/'sounds'/f'{style}_stretch_preview.wav'),winsound.SND_FILENAME|winsound.SND_ASYNC)
        self.status.set('Laptop preview: encouraging rise, a pause, then happy ending. Motion timing varies with taught poses.')
    def stretch_sound(self):
        try:
            cfg=self.config();self.send('sound',(6 if cfg['style']=='Robot chirps' else 7,cfg['volume']))
        except Exception as exc:messagebox.showerror('Settings',str(exc),parent=self.root)
    def water_sound(self):
        try:
            cfg=self.config();self.send('sound',(4 if cfg['style']=='Robot chirps' else 5,cfg['volume']))
        except Exception as exc:messagebox.showerror('Settings',str(exc),parent=self.root)
    def stop(self):
        winsound.PlaySound(None,0)
        if self.connected:self.busy=True;self.link.submit('stop');self.refresh()
    def release(self):
        if self.connected and messagebox.askokcancel('Support lamp','Support the lamp before releasing. It can fall when signals turn off.',parent=self.root):self.busy=True;self.power.set(False);self.link.submit('off');self.refresh()
    def poll(self):
        self.link.ui_alive=time.monotonic()
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='connected':
                    self.connected=True;self.busy=False;self.sound_count=data[1];self.sound_ready=data[1]>=4;self.connection.set(data[0]+' · '+('all sounds ready' if data[1]>=8 else 'slump/water ready; stretch update needed' if data[1]>=6 else 'install water-sound update' if data[1]>=4 else 'install lamp sound firmware'))
                    self.status.set('Connected. No movement or sound started. Teach poses when supported.')
                elif kind=='state':self.state=data
                elif kind=='phase':self.status.set(data)
                elif kind=='finished':self.busy=False;self.status.set(data)
                elif kind=='error':self.connected=False;self.busy=False;self.power.set(False);self.state=None;self.connection.set('Disconnected');self.status.set(data)
                elif kind=='closed':self.root.destroy();return
        except queue.Empty:pass
        self.refresh();self.root.after(50,self.poll)
    def close(self):
        if self.closing:return
        if self.state and any(self.state['active']) and not messagebox.askokcancel('Support the lamp','Closing releases outputs. Support the lamp first.',parent=self.root):return
        winsound.PlaySound(None,0);self.closing=True
        if self.connected:self.link.submit('close');self.refresh()
        else:self.root.destroy()

if __name__=='__main__':
    root=tk.Tk();LampDemo(root);root.mainloop()
