"""Calibrated side-view pose editor. Drawing is an estimate; no automatic hardware actions."""
import copy,json,math,pathlib,queue,time,tkinter as tk
import winsound
from tkinter import ttk,messagebox,simpledialog
from lamp_demo import LampLink,DEFAULT,validate,Cancelled,board_port
from live_control import base_command
from expressive_routines import build_gesture,sample_motion,trajectory_duration
HERE=pathlib.Path(__file__).resolve().parent
FILE=HERE/'visual-lamp.json'
PROFILES=HERE/'profiles'
SOUND_FILES=['robot_slump','robot_recover','music_slump','music_recover','robot_water','music_water','robot_stretch','music_stretch']
SOUND_SECONDS=[2.1,1.6,2.1,1.6,2.3,2.3,2.3,2.3]
COLORS=('#36b8bd','#f6b85a','#a89aed')
SOUNDS=['None','Robot slump','Robot happy','Music slump','Music happy','Robot water','Music water','Robot stretch','Music stretch']

def finite(x,lo,hi):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not lo<=x<=hi:raise ValueError(f'Use a number within {lo}..{hi}.')
    return x

def mapping(points):
    points=sorted(points)
    if len(points)<2:raise ValueError('Save at least two calibration points per joint.')
    if any(b[0]<=a[0] or b[1]==a[1] for a,b in zip(points,points[1:])):raise ValueError('Calibration needs different pulses and angles.')
    signs=[b[1]>a[1] for a,b in zip(points,points[1:])]
    if len(set(signs))!=1:raise ValueError('Angles must consistently increase or decrease as pulses increase.')
    return points

def interpolate(points,x,inverse=False):
    pts=mapping(points)
    if inverse:pts=sorted((a,p) for p,a in pts)
    x=max(pts[0][0],min(pts[-1][0],x))
    for (a,b),(c,d) in zip(pts,pts[1:]):
        if x<=c:return b+(d-b)*(x-a)/(c-a)
    return pts[-1][1]

def reverse_mapping(points,pulse):
    anchor=interpolate(points,pulse)
    return [[p,2*anchor-a] for p,a in points]

def full_range(points,center,lo=500,hi=2500):
    finite(center,-540,540)
    direction=1 if points[-1][1]>points[0][1] else -1
    return [[lo,center-direction*90],[hi,center+direction*90]]

def ensure_full_pulse_range(p):
    # Calibration describes geometry; it must not restrict electrical access.
    p['config']['low']=[500]*3;p['config']['high']=[2500]*3
    for i,points in enumerate(p['calibration']):
        if points[0][0]!=500 or points[-1][0]!=2500:
            pulse=p['config']['start'][i];direction=1 if points[-1][1]>points[0][1] else -1
            center=interpolate(points,pulse)-direction*180*((pulse-500)/2000-.5)
            center=(center+180)%360-180
            p['calibration'][i]=full_range(points,center)
            p['calibrated'][i]=False
    p['full_ranges']=[True]*3
    return p

def preview_motion(start,goal,seconds,cap,elapsed):
    distance=max(abs(a-b) for a,b in zip(start,goal))
    speed=max(10,min(cap,math.ceil(distance/max(.2,seconds))))
    pose=[round(a+min(abs(b-a),speed*elapsed)*(1 if b>=a else -1)) for a,b in zip(start,goal)]
    return pose,distance/speed if distance else 0

def fresh():
    p=dict(version=1,config=copy.deepcopy(DEFAULT),lengths=[150,150,65],
                calibration=[[[500,-90],[2500,90]],[[500,-90],[2500,90]],[[500,90],[2500,-90]]],
                calibrated=[False]*3,poses={},routine=[],base_reverse=True,direction_fix_20261030=True)
    return p

def upgrade_directions(p):
    if not p.get('direction_fix_20261030'):
        p['calibration'][2]=reverse_mapping(p['calibration'][2],p['config']['start'][2])
        p['calibrated'][2]=False;p.setdefault('matches',{}).pop('2',None)
        p['base_reverse']=True;p['direction_fix_20261030']=True
    if not p.get('lift_direction_fix_20261030'):
        p['calibration'][0]=reverse_mapping(p['calibration'][0],p['config']['start'][0])
        p['calibrated'][0]=False;p.setdefault('matches',{}).pop('0',None)
        p['lift_direction_fix_20261030']=True
    return p

def check_project(p):
    if p['version']!=1:raise ValueError('Unsupported visual project.')
    validate(p['config'])
    if len(p['lengths'])!=3 or len(p['calibration'])!=3 or len(p['calibrated'])!=3:raise ValueError('Expected three joints.')
    for length in p['lengths']:finite(length,10,500)
    for points in p['calibration']:
        for pulse,angle in points:finite(pulse,500,2500);finite(angle,-720,720)
        mapping(points)
    for pose in p['poses'].values():check_pose(pose,p['config'])
    for row in p['routine']:
        if row.get('type')=='base':
            base_command(row['direction'],row['speed'],row['neutral']);finite(row['seconds'],.1,10)
            continue
        check_pose(row['pulse'],p['config']);finite(row['seconds'],.1 if row.get('easing')=='quintic' else 1,30);finite(row['pause'],0,30)
        if row.get('easing')=='quintic':
            if len(row.get('delays',[]))!=3:raise ValueError('Expected three joint timing offsets.')
            for delay in row['delays']:finite(delay,0,.4)
        if type(row['sound'])!=int or not -1<=row['sound']<=7:raise ValueError('Invalid sound.')
    return p

def check_pose(pulse,cfg):
    if len(pulse)!=3 or any(type(v)!=int or not lo<=v<=hi for v,lo,hi in zip(pulse,cfg['low'],cfg['high'])):raise ValueError('Pose outside saved pulse limits.')

class VisualLink(LampLink):
    def perform(self,kind,payload):
        if isinstance(payload,dict) and payload.get('live'):
            self.live_drag(payload['cfg']);return
        rows,cfg,count=payload
        validate(cfg)
        for row in rows:
            if row.get('type')=='base':
                base_command(row['direction'],row['speed'],row['neutral']);finite(row['seconds'],.1,10)
                continue
            check_pose(row['pulse'],cfg);finite(row['seconds'],.1 if row.get('easing')=='quintic' else 1,30);finite(row['pause'],0,30)
            if row['sound']>=count:raise ValueError('Board firmware does not include the selected sound.')
        self.exchange('arm_live status')
        if any(row.get('type')!='base' for row in rows) and (self.state['active'][:3]!=[1,1,1] or self.state['base_spin']):raise ValueError('Set the initial pose first and keep the base stopped.')
        pending=None
        for n,row in enumerate(rows,1):
            self.check();self.emit('phase',f"Checkpoint {n}/{len(rows)} · {row['name']}")
            if row.get('type')=='base':
                self.turn_base(row);continue
            if row.get('easing')=='quintic':
                if row['sound']>=0:
                    if pending is not None:self.finish_sound(pending)
                    self.start_sound(row['sound'],cfg['volume']);pending=row['sound']
                self.expressive_glide(row,cfg);self.hold_pause(row['pause']);continue
            self.glide(row['pulse'],row['seconds'],cfg)
            if row['sound']>=0:
                self.start_sound(row['sound'],cfg['volume']);self.finish_sound(row['sound'])
            self.hold_pause(row['pause'])
        if pending is not None:self.finish_sound(pending)
        self.emit('finished','Done. Last commanded pose is holding.')
    def expressive_glide(self,row,cfg):
        start=self.state['pulse'][:3].copy();begin=time.monotonic()
        while True:
            self.check();pose,duration=sample_motion(start,row,time.monotonic()-begin,cfg['max_speed'])
            self.exchange('arm_live glide '+' '.join(map(str,(*pose,cfg['max_speed']))))
            if time.monotonic()-begin>=duration:break
            self.wait_until(time.monotonic()+.05)
        # Account for transport lag without jumping to an unacknowledged target.
        self.glide(row['pulse'],.2,cfg)
    def live_drag(self,cfg):
        validate(cfg);self.exchange('arm_live status')
        if self.state['active'][:3]!=[1,1,1] or self.state['base_spin']:raise ValueError('Engage the three joints first; stop the base.')
        try:
            while self.live_held:
                self.check();target,speed,updated=self.live_target
                if time.monotonic()-updated>.3:break
                check_pose(target,cfg);finite(speed,10,600)
                self.exchange('arm_live glide '+' '.join(map(str,(*target,min(cfg['max_speed'],int(speed))))))
                self.wait_until(time.monotonic()+.05)
        finally:
            self.exchange('arm_live freeze')
        self.emit('finished','Live drag stopped; current commanded pose held.')
    def turn_base(self,row):
        deadline=time.monotonic()+row['seconds']
        try:
            while time.monotonic()<deadline:
                self.check()
                if row.get('hold') and not self.base_held:break
                self.exchange(base_command(row['direction'],row['speed'],row['neutral']))
                self.wait_until(time.monotonic()+.08)
        finally:
            self.exchange(base_command(0,0,row['neutral']))

class App:
    def __init__(self,root):
        self.root=root;self.p=fresh();self.events=queue.Queue();self.state=None;self.connected=False;self.busy=False;self.count=0;self.dragging=None;self.preview_token=0;self.match_angles=None;self.match_pulse=None
        self.live_stream=False;self.control_held=False;self.last_live=None;self.real_angles=None;self.real_dragging=None
        self.previewing=False;self.preview_plan=None
        self.real_reference=None
        self.closing=False;self.disconnecting=False;self.retry_at=time.monotonic()+1.5;self.retry_count=0
        self.auto_connect=tk.BooleanVar(value=True)
        self.range_edit=tk.BooleanVar(value=False);self.range_center=tk.DoubleVar(value=0);self.range_dragging=False;self.range_joint=0
        self.joint=tk.StringVar(value='Lift');self.range_summary=tk.StringVar(value='Select a joint to see and adjust its arc.')
        self.status=tk.StringVar(value='Preview only. Calibrate the drawing before using it to plan real movements.')
        try:
            if FILE.exists():self.p=check_project(json.loads(FILE.read_text(encoding='utf-8')))
        except Exception as e:self.status.set('Saved visual project ignored: '+str(e))
        upgrade_directions(self.p)
        ensure_full_pulse_range(self.p)
        self.link=VisualLink(lambda *e:self.events.put(e))
        root.title('Lamp Studio · visual poses & routines');root.geometry('1160x820');root.minsize(1060,760)
        st=ttk.Style();st.theme_use('clam');st.configure('TButton',padding=6,font=('Segoe UI',10));st.configure('TLabel',font=('Segoe UI',10))
        top=ttk.Frame(root,padding=12);top.pack(fill='x')
        ttk.Label(top,text='Lamp Studio',font=('Segoe UI',22,'bold')).pack(side='left')
        self.connection=tk.StringVar(value='Offline · preview works');ttk.Label(top,textvariable=self.connection).pack(side='left',padx=20)
        ttk.Button(top,text='Connect board',command=lambda:self.send('connect')).pack(side='right')
        ttk.Button(top,text='Disconnect…',command=self.disconnect_board).pack(side='right',padx=5)
        ttk.Checkbutton(top,text='Auto reconnect USB',variable=self.auto_connect).pack(side='right',padx=5)
        profilebar=ttk.Frame(root,padding=(12,0,12,6));profilebar.pack(fill='x')
        self.profile_name=tk.StringVar(value=self.p.get('profile_name','Lamp Cardboard Prototype'))
        self.profile_box=ttk.Combobox(profilebar,textvariable=self.profile_name,width=28);self.profile_box.pack(side='left')
        ttk.Button(profilebar,text='Save profile',command=lambda:self.attempt(self.save_profile)).pack(side='left',padx=5)
        ttk.Button(profilebar,text='Load profile',command=lambda:self.attempt(self.load_profile)).pack(side='left',padx=5)
        ttk.Button(profilebar,text='▶ Run previewed plan',command=lambda:self.attempt(self.run_previewed)).pack(side='right')
        body=ttk.Panedwindow(root,orient='horizontal');body.pack(fill='both',expand=True,padx=12)
        left=ttk.Frame(body);right=ttk.Frame(body);body.add(left,weight=1);body.add(right,weight=1)
        ttk.Label(left,text='CONTROL ARM · drag to command',font=('Segoe UI',11,'bold')).pack(anchor='w')
        toolbar=ttk.LabelFrame(left,text='Movement arc · always available here',padding=5);toolbar.pack(fill='x',pady=4)
        row=ttk.Frame(toolbar);row.pack(fill='x')
        ttk.Combobox(row,textvariable=self.joint,values=['Lift','Middle','Head'],state='readonly',width=9).pack(side='left',padx=3)
        ttk.Button(row,text='Use full 180°',command=lambda:self.attempt(self.restore_range)).pack(side='left',padx=3)
        ttk.Button(row,text='Rotate arc…',command=lambda:self.attempt(self.open_range)).pack(side='left',padx=3)
        row=ttk.Frame(toolbar);row.pack(fill='x',pady=3)
        ttk.Button(row,text='↶ 5°',command=lambda:self.attempt(lambda:self.nudge_range(-5))).pack(side='left')
        ttk.Button(row,text='5° ↷',command=lambda:self.attempt(lambda:self.nudge_range(5))).pack(side='left',padx=3)
        ttk.Button(row,text='Save arc',command=lambda:self.attempt(self.save_range)).pack(side='left',padx=3)
        ttk.Button(row,text='Cancel',command=self.cancel_range).pack(side='left',padx=3)
        ttk.Button(row,text='Flip lamp face',command=lambda:self.attempt(self.flip_face)).pack(side='left',padx=3)
        ttk.Label(toolbar,textvariable=self.range_summary,wraplength=470).pack(anchor='w')
        self.canvas=tk.Canvas(left,bg='#12232e',highlightthickness=0,width=490,height=230);self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw());self.canvas.bind('<Button-1>',self.press);self.canvas.bind('<B1-Motion>',self.drag);self.canvas.bind('<ButtonRelease-1>',lambda e:self.end_control())
        self.canvas.bind('<Leave>',lambda e:self.end_control())
        self.live_enabled=tk.BooleanVar();ttk.Checkbutton(left,text='Enable live dragging (once per connection)',variable=self.live_enabled,command=self.toggle_live).pack(anchor='w',pady=3)
        self.live_max=tk.StringVar(value='600');self.field(left,'Live speed limit (µs/s, 10–600)',self.live_max)
        ttk.Label(left,text='OBSERVED ARM · adjust to match the real lamp',font=('Segoe UI',11,'bold')).pack(anchor='w')
        self.real_canvas=tk.Canvas(left,bg='#25343b',highlightthickness=0,width=490,height=230);self.real_canvas.pack(fill='both',expand=True)
        self.real_canvas.bind('<Configure>',lambda e:self.draw_real());self.real_canvas.bind('<Button-1>',lambda e:self.attempt(lambda:self.real_press(e)))
        self.real_canvas.bind('<B1-Motion>',self.real_drag);self.real_canvas.bind('<ButtonRelease-1>',lambda e:self.attempt(self.real_release))
        ttk.Label(left,text='Top: estimated command. Bottom: your observation, saved as calibration.\nNo position sensors. Live speed follows your drag, capped at600µs/s.',wraplength=490).pack(pady=4)
        self.pulses=[]
        for i,name in enumerate(('Lift · GPIO12','Middle · GPIO10','Head · GPIO11')):
            row=ttk.Frame(left);row.pack(fill='x',pady=3);ttk.Label(row,text=name,width=18).pack(side='left')
            v=tk.DoubleVar(value=self.p.get('preview_pulse',self.p['config']['start'])[i]);self.pulses.append(v)
            slider=ttk.Scale(row,from_=self.p['config']['low'][i],to=self.p['config']['high'][i],variable=v,command=lambda _,j=i:self.slider_changed());slider.pack(side='left',fill='x',expand=True)
            slider.bind('<ButtonPress-1>',lambda e:self.start_control(),add='+');slider.bind('<ButtonRelease-1>',lambda e:self.end_control(),add='+')
            slider.bind('<Leave>',lambda e:self.end_control(),add='+')
            ent=ttk.Entry(row,textvariable=v,width=8);ent.pack(side='left',padx=5);ent.bind('<Return>',lambda e:self.draw())
        tabs=ttk.Notebook(right);tabs.pack(fill='both',expand=True)
        pose=ttk.Frame(tabs,padding=10);cal=ttk.Frame(tabs,padding=10);routine=ttk.Frame(tabs,padding=10);base=ttk.Frame(tabs,padding=10)
        tabs.add(pose,text='Pose control');tabs.add(cal,text='Calibrate drawing');tabs.add(routine,text='Routine')
        tabs.add(base,text='Rotating base')
        ttk.Label(base,text='Rotating base · GPIO15',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=8)
        ttk.Label(base,text='Continuous servo: these buttons control speed, not angle.\nHold an arrow to turn; release it to stop. Watch cable twist.\nUse the power checkbox in Pose control before moving.',wraplength=470).pack(anchor='w',pady=8)
        self.base_speed=tk.StringVar(value='5');self.base_neutral=tk.StringVar(value='1500');self.base_seconds=tk.StringVar(value='1')
        self.field(base,'Turn speed % (1–100)',self.base_speed)
        self.field(base,'Stop pulse µs (1400–1600)',self.base_neutral)
        self.base_reverse=tk.BooleanVar(value=self.p.get('base_reverse',True));ttk.Checkbutton(base,text='Swap left / right directions',variable=self.base_reverse,command=self.save_base_direction).pack(anchor='w',pady=6)
        row=ttk.Frame(base);row.pack(fill='x',pady=12)
        for label,d in [('← Hold left',-1),('Hold right →',1)]:
            button=ttk.Button(row,text=label);button.pack(side='left',expand=True,fill='x')
            button.bind('<ButtonPress-1>',lambda e,d=d:self.attempt(lambda:self.base_hold(d)))
            button.bind('<ButtonRelease-1>',lambda e:self.base_release());button.bind('<Leave>',lambda e:self.base_release())
        root.bind_all('<ButtonRelease-1>',lambda e:self.base_release(),add='+')
        root.bind('<FocusOut>',lambda e:root.after(20,lambda:self.base_release() if root.focus_displayof() is None else None),add='+')
        ttk.Button(base,text='Stop base',command=self.base_release).pack(fill='x',pady=5)
        self.base_status=tk.StringVar(value='Base idle · heading unknown')
        ttk.Label(base,textvariable=self.base_status,wraplength=470).pack(anchor='w',pady=12)
        ttk.Separator(base).pack(fill='x',pady=10)
        self.field(base,'Timed turn duration (0.1–10 seconds)',self.base_seconds)
        row=ttk.Frame(base);row.pack(fill='x',pady=8)
        ttk.Button(row,text='Add left turn to routine',command=lambda:self.attempt(lambda:self.add_base(-1))).pack(side='left',expand=True,fill='x')
        ttk.Button(row,text='Add right turn to routine',command=lambda:self.attempt(lambda:self.add_base(1))).pack(side='left',expand=True,fill='x')
        ttk.Label(base,text='Turns are separate timed checkpoints. The three bending joints\nhold their last commands while the base turns.\nNo encoder: heading and cable twist are not measured.\nIf it creeps at stop, adjust Stop pulse a few µs and test again.\nHolding is limited to ten seconds per press.',wraplength=470).pack(anchor='w',pady=10)
        cal_host=cal
        cal_scroll=tk.Canvas(cal_host,highlightthickness=0)
        cal_bar=ttk.Scrollbar(cal_host,orient='vertical',command=cal_scroll.yview)
        cal_scroll.configure(yscrollcommand=cal_bar.set)
        cal_bar.pack(side='right',fill='y');cal_scroll.pack(side='left',fill='both',expand=True)
        cal=ttk.Frame(cal_scroll);cal_window=cal_scroll.create_window(0,0,window=cal,anchor='nw')
        cal.bind('<Configure>',lambda e:cal_scroll.configure(scrollregion=cal_scroll.bbox('all')))
        cal_scroll.bind('<Configure>',lambda e:cal_scroll.itemconfigure(cal_window,width=e.width))
        self.power=tk.BooleanVar();ttk.Checkbutton(pose,text='External servo power / common ground checked; lamp supported',variable=self.power).pack(anchor='w')
        self.seconds=tk.StringVar(value='6');self.speed=tk.StringVar(value='60')
        self.field(pose,'Move time (seconds)',self.seconds);self.field(pose,'Speed cap (µs/second, 10–600)',self.speed)
        ttk.Button(pose,text='Engage at preview pose…',command=self.engage).pack(fill='x',pady=6)
        ttk.Button(pose,text='Move gradually to preview pose',command=self.move).pack(fill='x',pady=6)
        ttk.Button(pose,text='Use last commanded pose in preview',command=self.use_current).pack(fill='x',pady=6)
        ttk.Label(pose,text='Named checkpoints',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(12,4))
        self.poses=tk.Listbox(pose,height=7,exportselection=False);self.poses.pack(fill='both',expand=True)
        for text,fn in [('Save preview as checkpoint',self.save_pose),('Load selected into preview',self.load_pose),('Delete selected checkpoint',self.delete_pose)]:ttk.Button(pose,text=text,command=fn).pack(fill='x',pady=3)
        ttk.Label(cal,text='Make the picture match your lamp',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=6)
        ttk.Label(cal,text='1. Choose the joint that looks wrong.\n2. If it bends the wrong way, press Reverse direction.\n3. Match the picture at two different robot positions.',wraplength=470).pack(anchor='w',pady=6)
        ttk.Combobox(cal,textvariable=self.joint,values=['Lift','Middle','Head'],state='readonly').pack(fill='x',pady=8)
        self.joint.trace_add('write',lambda *_:self.cal_list())
        ttk.Button(cal,text='↔ Reverse direction for this joint',command=lambda:self.attempt(self.reverse_joint)).pack(fill='x',pady=6)
        self.match_text=tk.StringVar(value='Ready. Position the real lamp first, then start matching.')
        ttk.Label(cal,textvariable=self.match_text,wraplength=470).pack(anchor='w',pady=8)
        ttk.Button(cal,text='1. Match picture to current lamp position',command=lambda:self.attempt(self.begin_match)).pack(fill='x',pady=5)
        ttk.Label(cal,text='While matching: drag the colored endpoint, or use these buttons.\nOnly the picture changes; the robot stays still.',wraplength=470).pack(anchor='w',pady=5)
        row=ttk.Frame(cal);row.pack(fill='x')
        ttk.Button(row,text='↶ Bend picture left',command=lambda:self.bend_match(-3)).pack(side='left',expand=True,fill='x')
        ttk.Button(row,text='Bend picture right ↷',command=lambda:self.bend_match(3)).pack(side='left',expand=True,fill='x')
        ttk.Button(cal,text='2. Picture matches — save this position',command=lambda:self.attempt(self.finish_match)).pack(fill='x',pady=5)
        ttk.Button(cal,text='Cancel picture matching',command=self.cancel_match).pack(fill='x',pady=3)
        ttk.Label(cal,text='Then move the same joint a little using the pulse slider + Move.\nRepeat matching there to teach its direction and travel.\nStart with Lift, then Middle, then Head.',wraplength=470).pack(anchor='w',pady=8)
        advanced=ttk.Frame(cal)
        ttk.Button(cal,text='Show / hide advanced numbers & link lengths',command=lambda:advanced.pack_forget() if advanced.winfo_manager() else advanced.pack(fill='x')).pack(fill='x',pady=8)
        cal=advanced
        self.angle=tk.StringVar(value='0');self.field(cal,'Observed relative angle (degrees)',self.angle)
        self.pair=tk.StringVar(value='1000,-30; 1600,30')
        self.field(cal,'Two observed points: pulse,angle; pulse,angle',self.pair)
        ttk.Button(cal,text='Replace this joint’s calibration with these two points',command=lambda:self.attempt(self.replace_cal)).pack(fill='x',pady=4)
        ttk.Button(cal,text='Save angle at this preview pulse',command=self.save_cal).pack(fill='x',pady=6)
        self.points=tk.Listbox(cal,height=6,exportselection=False);self.points.pack(fill='x')
        ttk.Button(cal,text='Remove selected calibration point',command=self.remove_cal).pack(fill='x',pady=4)
        ttk.Label(cal,text='Replace BOTH estimated endpoint points with observed points.\nUse at least two different pulses per joint. More points refine the fit.\nOutside observed calibration, the drawing clamps to the nearest angle.',wraplength=490).pack(anchor='w',pady=8)
        self.confirmed=tk.BooleanVar();ttk.Checkbutton(cal,text='This joint’s calibration points have been checked on the lamp',variable=self.confirmed,command=self.confirm_cal).pack(anchor='w')
        self.lengths=[tk.StringVar(value=str(v)) for v in self.p['lengths']]
        for label,v in zip(('Lower link length','Upper link length','Head indicator length'),self.lengths):self.field(cal,label+' (same units)',v)
        ttk.Button(cal,text='Save link lengths',command=self.save_lengths).pack(fill='x',pady=4)
        ranges=ttk.Frame(tabs,padding=10);tabs.add(ranges,text='Joint range')
        ttk.Label(ranges,text='Place the 180° movement sector',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=8)
        ttk.Label(ranges,text='Click a joint in the top picture, or choose one below.\nThe colored arc shows its current estimated range.\nEdit mode lets you rotate a full 180° sector around its pivot.\nEditing never moves the real lamp.',wraplength=470).pack(anchor='w',pady=8)
        box=ttk.Combobox(ranges,textvariable=self.joint,values=['Lift','Middle','Head'],state='readonly');box.pack(fill='x',pady=6)
        ttk.Checkbutton(ranges,text='Edit 180° range (live movement locked)',variable=self.range_edit,command=lambda:self.attempt(self.toggle_range)).pack(anchor='w',pady=8)
        ttk.Label(ranges,text='Drag the white RANGE handle around the pivot,\nor adjust the rotation slider below.',wraplength=470).pack(anchor='w',pady=8)
        ttk.Scale(ranges,from_=-360,to=360,variable=self.range_center,command=lambda _:self.draw()).pack(fill='x',pady=8)
        row=ttk.Frame(ranges);row.pack(fill='x')
        for label,amount in [('↶ Rotate 5°',-5),('Rotate 5° ↷',5)]:ttk.Button(row,text=label,command=lambda d=amount:(self.range_center.set(self.range_center.get()+d),self.draw())).pack(side='left',expand=True,fill='x')
        ttk.Button(ranges,text='Save full 180° range for selected joint',command=lambda:self.attempt(self.save_range)).pack(fill='x',pady=12)
        self.range_info=tk.StringVar();ttk.Label(ranges,textvariable=self.range_info,wraplength=470).pack(anchor='w',pady=6)
        ttk.Label(ranges,text='This maps the configured pulse limits to a 180° drawing.\nIt cannot extend the physical servo or guarantee clearance.\nKeep the robot supported and test slowly after saving.\nYour observed-arm adjustments will align this sector without shrinking it.',wraplength=470).pack(anchor='w',pady=10)
        actions=ttk.Frame(tabs,padding=10);tabs.add(actions,text='Three actions')
        ttk.Label(actions,text='Slump · Water · Stretch',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=8)
        ttk.Label(actions,text='Expressive gestures · one click plays the whole preview.\nRest is your home pose; real checkpoints take priority.\nStarter guesses use small movements shaped by the lamp model.',wraplength=470).pack(anchor='w',pady=8)
        self.roles={};self.role_boxes=[]
        for key in ('Rest','Slump','Water','Stretch'):
            row=ttk.Frame(actions);row.pack(fill='x',pady=4);ttk.Label(row,text=key,width=10).pack(side='left')
            var=tk.StringVar(value=self.p.get('roles',{}).get(key,''));self.roles[key]=var
            box=ttk.Combobox(row,textvariable=var,state='readonly');box.pack(side='left',fill='x',expand=True);self.role_boxes.append(box)
        ttk.Button(actions,text='Save action checkpoint choices',command=lambda:self.attempt(self.save_roles)).pack(fill='x',pady=6)
        ttk.Button(actions,text='Load editable starter checkpoints',command=lambda:self.attempt(self.load_action_starters)).pack(fill='x',pady=6)
        self.action_style=tk.StringVar(value='Robot chirps');ttk.Combobox(actions,textvariable=self.action_style,values=['Robot chirps','Musical tones'],state='readonly').pack(fill='x',pady=8)
        for key in ('Slump','Water','Stretch'):
            row=ttk.Frame(actions);row.pack(fill='x',pady=6)
            ttk.Button(row,text='▶ Play '+key+' preview',command=lambda k=key:self.attempt(lambda:self.preview(self.action_rows(k)))).pack(side='left',expand=True,fill='x')
            ttk.Button(row,text='Run '+key+' + sound',command=lambda k=key:self.attempt(lambda:self.run_action(k))).pack(side='left',expand=True,fill='x')
        self.playback_text=tk.StringVar(value='One click plays the full animated gesture with sound.')
        ttk.Label(actions,textvariable=self.playback_text,wraplength=470).pack(anchor='w',pady=(10,4))
        self.playback_progress=tk.DoubleVar(value=0);ttk.Progressbar(actions,variable=self.playback_progress,maximum=100).pack(fill='x',pady=4)
        ttk.Button(profilebar,text='▶ Actions',command=lambda:tabs.select(actions)).pack(side='left',padx=5)
        tabs.select(actions)
        ttk.Label(routine,text='Select a checkpoint in Pose control, then add it here.\nEach row stores its own pulse values. Sound plays on arrival.',wraplength=490).pack(anchor='w')
        self.pause=tk.StringVar(value='1');self.sound=tk.StringVar(value='None');self.field(routine,'Pause after sound (seconds)',self.pause)
        ttk.Combobox(routine,textvariable=self.sound,values=SOUNDS,state='readonly').pack(fill='x',pady=6)
        ttk.Button(routine,text='Append selected checkpoint',command=self.append).pack(fill='x',pady=4)
        self.rows=tk.Listbox(routine,height=9,exportselection=False);self.rows.pack(fill='both',expand=True)
        row=ttk.Frame(routine);row.pack(fill='x')
        for label,fn in [('↑',lambda:self.reorder(-1)),('↓',lambda:self.reorder(1)),('Remove',self.remove_row)]:ttk.Button(row,text=label,command=fn).pack(side='left',expand=True,fill='x')
        ttk.Button(routine,text='Preview routine on screen',command=self.preview).pack(fill='x',pady=6)
        ttk.Button(routine,text='Run routine on robot',command=self.run).pack(fill='x',pady=6)
        bottom=ttk.Frame(root,padding=12);bottom.pack(fill='x')
        ttk.Button(bottom,text='STOP motion + sound + preview',command=self.stop).pack(side='left')
        ttk.Button(bottom,text='Release outputs…',command=self.release).pack(side='left',padx=8)
        ttk.Label(bottom,textvariable=self.status,wraplength=700).pack(side='left',padx=10)
        self.apply_ui_preferences();self.refresh_profiles()
        root.protocol('WM_DELETE_WINDOW',self.close);self.refresh_lists();self.cal_list();self.draw();root.after(50,self.poll)
        root.bind_all('<ButtonRelease-1>',lambda e:self.end_control(),add='+')
        root.bind('<FocusOut>',lambda e:root.after(20,lambda:self.end_control() if root.focus_displayof() is None else None),add='+')
    def field(self,parent,label,var):
        row=ttk.Frame(parent);row.pack(fill='x',pady=4);ttk.Label(row,text=label).pack(side='left');ttk.Entry(row,textvariable=var,width=9).pack(side='right')
    def attempt(self,fn):
        try:return fn()
        except Exception as e:messagebox.showerror('Lamp Studio',str(e),parent=self.root)
    def save(self):
        if self.previewing:self.cancel_preview()
        if hasattr(self,'action_style'):self.p['studio_ui']=self.capture_ui()
        ensure_full_pulse_range(self.p);check_project(self.p);tmp=FILE.with_suffix('.tmp');tmp.write_text(json.dumps(self.p,indent=2),encoding='utf-8');tmp.replace(FILE)
    def refresh_profiles(self):
        names=[]
        for path in PROFILES.glob('*.json'):
            if path.name.endswith('.previous.json'):continue
            try:names.append(json.loads(path.read_text(encoding='utf-8'))['profile_name'])
            except (ValueError,KeyError):pass
        self.profile_box.configure(values=sorted(names))
    def capture_ui(self):
        return dict(seconds=self.seconds.get(),speed=self.speed.get(),live_max=self.live_max.get(),base_speed=self.base_speed.get(),base_neutral=self.base_neutral.get(),base_seconds=self.base_seconds.get(),action_style=self.action_style.get())
    def apply_ui_preferences(self):
        for key,value in self.p.get('studio_ui',{}).items():
            if key in ('seconds','speed','live_max','base_speed','base_neutral','base_seconds','action_style'):getattr(self,key).set(value)
        self.live_enabled.set(False)
    def profile_path(self,name):
        if not name.strip() or any(ch in name for ch in '/\\:*?"<>|') or name.rstrip(' .')!=name:raise ValueError('Choose a simple profile name without path characters.')
        return PROFILES/(name+'.json')
    def save_profile(self):
        name=self.profile_name.get().strip();path=self.profile_path(name)
        self.p['preview_pulse']=self.pulse();self.p['observed_angles']=copy.deepcopy(self.real_angles)
        self.p['config']=self.config();self.p['studio_ui']=self.capture_ui();self.p['base_reverse']=self.base_reverse.get();self.p['profile_name']=name
        self.save();PROFILES.mkdir(exist_ok=True)
        if path.exists():path.with_suffix('.previous.json').write_text(path.read_text(encoding='utf-8'),encoding='utf-8')
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(self.p,indent=2),encoding='utf-8');tmp.replace(path)
        self.refresh_profiles();self.status.set('Profile saved: '+name+'. All adjustment tools remain available.')
    def load_profile(self):
        if self.connected or self.busy:raise ValueError('Use Disconnect first (support the lamp), then load the profile.')
        candidate=check_project(json.loads(self.profile_path(self.profile_name.get().strip()).read_text(encoding='utf-8')))
        self.cancel_preview();self.cancel_match();self.cancel_range();self.p=upgrade_directions(candidate);ensure_full_pulse_range(self.p)
        self.base_reverse.set(self.p.get('base_reverse',True));self.real_angles=self.p.get('observed_angles')
        for var,value in zip(self.pulses,self.p.get('preview_pulse',self.p['config']['start'])):var.set(value)
        for var,value in zip(self.lengths,self.p['lengths']):var.set(str(value))
        for key,var in self.roles.items():var.set(self.p.get('roles',{}).get(key,''))
        self.apply_ui_preferences();self.save();self.refresh_lists();self.cal_list();self.draw();self.status.set('Profile loaded; live control remains off.')
    def pulse(self):
        v=[round(finite(x.get(),lo,hi)) for x,lo,hi in zip(self.pulses,self.p['config']['low'],self.p['config']['high'])];check_pose(v,self.p['config']);return v
    def config(self):
        cfg=copy.deepcopy(self.p['config']);cfg['max_speed']=int(self.speed.get());validate(cfg);return cfg
    def coords(self,pulse,canvas=None,angles=None):
        if angles is None:angles=self.match_angles if self.match_angles is not None else [interpolate(p,x) for p,x in zip(self.p['calibration'],pulse)]
        canvas=canvas or self.canvas
        w=max(300,canvas.winfo_width());h=max(150,canvas.winfo_height())
        # Fit the full reach on either side and above/below the pivot.
        scale=min(w*.43,h*.43)/sum(self.p['lengths']);pts=[(w/2,h/2)];a=-90
        for angle,length in zip(angles,self.p['lengths']):
            a+=angle;x,y=pts[-1];pts.append((x+length*scale*math.cos(math.radians(a)),y+length*scale*math.sin(math.radians(a))))
        return pts
    def lamp_details(self,c,pts):
        # J1 is the mount pivot, J2 the elbow, J3 the head hinge.
        # Endpoint handles still control their preceding joint, as before.
        x,y=pts[0]
        c.create_line(x-42,y+33,x+42,y+33,fill='#607985',width=2)
        c.create_polygon(x-24,y+27,x-17,y+9,x+17,y+9,x+24,y+27,fill='#647d87',outline='#a8c0ca',width=2)
        c.create_oval(x-24,y+22,x+24,y+33,fill='#445e6a',outline='#a8c0ca')
        c.create_text(x,y+44,text='BASE · rotating pedestal',fill='#c7d9e3',font=('Segoe UI',8))
        for i,name in enumerate(('lower arm','upper arm')):
            a,b=pts[i],pts[i+1]
            c.create_text((a[0]+b[0])/2,(a[1]+b[1])/2-14,text=name,fill='#d8e5ec',font=('Segoe UI',8))
        for i,(x,y) in enumerate(pts[:3]):
            c.create_oval(x-5,y-5,x+5,y+5,fill='#12232e',outline=COLORS[i],width=3)
            c.create_text(x-9,y-10,text=('J1 lift','J2 elbow','J3 head tilt')[i],anchor='e',fill=COLORS[i],font=('Segoe UI',8,'bold'))
        # The final link describes the head orientation. Face may be flipped
        # independently of the servo map to match the physical shade mounting.
        x,y=pts[3];px,py=pts[2];length=max(.001,math.hypot(x-px,y-py));sign=self.p.get('head_face_sign',1)
        ux,uy=(x-px)/length*sign,(y-py)/length*sign;nx,ny=-uy,ux
        def point(along,side):return (x+along*ux+side*nx,y+along*uy+side*ny)
        front=point(13,0)
        c.create_polygon(*point(15,-10),*point(50,-22),*point(50,22),*point(15,10),fill='#e7c86d',stipple='gray75',outline='')
        c.create_polygon(*point(-13,-7),*point(12,-13),*point(12,13),*point(-13,7),fill='#e7b45d',outline='#ffe5a0',width=2)
        c.create_line(*point(13,-12),*point(13,12),fill='#fff9d8',width=4)
        c.create_line(*front,*point(62,0),fill='#fff0a5',width=2,arrow='last')
        c.create_text(*point(72,0),text='FRONT',fill='#fff0a5',font=('Segoe UI',8,'bold'))
        c.create_text(x,y-25,text='LAMP HEAD',fill='#fff0a5',font=('Segoe UI',8,'bold'))
        # A small center dot remains available as the last drag handle.
        c.create_oval(x-4,y-4,x+4,y+4,fill=COLORS[2],outline='white')
    def flip_face(self):
        if self.busy:raise ValueError('Wait for the movement to finish before changing the model.')
        self.cancel_preview();self.end_control();self.live_enabled.set(False)
        self.p['head_face_sign']=-self.p.get('head_face_sign',1);self.save();self.draw()
        self.status.set('Lamp front flipped in both pictures. Servo calibration and checkpoint pulses unchanged. Save profile to retain this in the named snapshot.')
    def draw(self):
        try:
            pulse=self.pulse();c=self.canvas;c.delete('all');pts=self.coords(pulse);self.xy=pts
            x,y=pts[0];c.create_rectangle(x-24,y+8,x+24,y+24,fill='#415762',outline='')
            if self.match_angles is None and self.state and all(self.state['pulse'][:3]):
                q=self.coords(self.state['pulse'][:3]);c.create_line(*[v for pt in q for v in pt],fill='#6e8290',width=3,dash=(5,5))
            for i in range(3):
                c.create_line(*pts[i],*pts[i+1],fill=COLORS[i],width=10,capstyle='round');x,y=pts[i+1];c.create_oval(x-10,y-10,x+10,y+10,fill=COLORS[i],outline='#fff',width=2)
            self.lamp_details(c,pts)
            self.draw_range(pts)
            label='MATCHING PICTURE ONLY · robot stays still' if self.match_angles is not None else 'Calibrated estimate' if all(self.p['calibrated']) else 'UNCALIBRATED · drawing directions are estimates'
            c.create_text(16,20,text=label,anchor='w',fill='#c7d9e3',font=('Segoe UI',11));c.create_text(16,44,text='Preview pulses: '+' / '.join(map(str,pulse))+' µs',anchor='w',fill='#c7d9e3')
            self.draw_real()
        except (ValueError,tk.TclError):pass
    def draw_real(self):
        if not hasattr(self,'real_canvas') or not self.pulses:return
        try:
            reference=self.real_reference if self.real_reference is not None else self.pulse()
            angles=self.real_angles if self.real_angles is not None else [interpolate(p,v) for p,v in zip(self.p['calibration'],reference)]
            c=self.real_canvas;c.delete('all');pts=self.coords(self.pulse(),c,angles);self.real_xy=pts
            for i in range(3):
                c.create_line(*pts[i],*pts[i+1],fill=COLORS[i],width=8,capstyle='round');x,y=pts[i+1];c.create_oval(x-9,y-9,x+9,y+9,fill=COLORS[i],outline='white')
            self.lamp_details(c,pts)
            c.create_text(10,14,text='YOUR OBSERVATION · drag a joint, release to teach' if self.real_angles is not None else 'Not observed yet · drag to match reality',anchor='w',fill='white')
        except (ValueError,tk.TclError):pass
    def toggle_live(self):
        if self.range_edit.get():self.live_enabled.set(False);self.status.set('Save the range before enabling live control.');return
        if not self.live_enabled.get():self.end_control();return
        if not self.connected or not self.power.get() or not self.state or self.state['active'][:3]!=[1,1,1] or self.busy:
            self.live_enabled.set(False);self.status.set('Connect, check power and engage the supported lamp once before enabling live control.');return
        self.status.set('Live dragging enabled. Drag top arm or pulse sliders; release to stop. Speed capped at600µs/s.')
    def start_control(self):
        self.control_held=True;self.last_live=(self.pulse(),time.monotonic());self.preview_token+=1
    def end_control(self):
        self.control_held=False;self.dragging=None;self.link.live_held=False;self.range_dragging=False
    def slider_changed(self):
        self.draw()
        if self.control_held:self.attempt(self.publish_live)
    def publish_live(self):
        if self.previewing:return
        if not self.live_enabled.get() or not self.control_held:return
        if self.match_angles is not None or self.real_dragging is not None or self.range_edit.get():return
        if self.busy and not self.live_stream:return
        if not self.connected or not self.power.get():self.live_enabled.set(False);self.end_control();return
        now=time.monotonic();pulse=self.pulse();previous,when=self.last_live or (pulse,now-.05)
        distance=max(abs(a-b) for a,b in zip(pulse,previous))
        if not distance:
            if self.live_stream:
                target,speed,_=self.link.live_target;self.link.live_target=(target,speed,now)
            return
        speed=max(10,min(600,round(distance/max(.015,now-when))))
        self.last_live=(pulse,now);self.link.live_target=(pulse,speed,now);self.link.live_held=True
        if not self.live_stream:
            cfg=self.config();cfg['max_speed']=int(self.live_max.get());validate(cfg)
            self.live_stream=True;self.send('slump',dict(live=True,cfg=cfg))
    def real_press(self,e):
        self.cancel_preview()
        self.end_control()
        if self.busy:raise ValueError('Let movement stop before recording the real position.')
        self.preview_token+=1
        if self.connected:
            if not self.state or self.state['active'][:3]!=[1,1,1] or any(self.state['moving'][:3]):raise ValueError('Wait for the lamp to hold still before matching it.')
            self.real_pulse=self.state['pulse'][:3].copy()
        else:self.real_pulse=self.pulse()
        if self.real_angles is None:self.real_angles=[interpolate(p,v) for p,v in zip(self.p['calibration'],self.real_pulse)]
        self.draw_real();i=min(range(3),key=lambda j:math.hypot(e.x-self.real_xy[j+1][0],e.y-self.real_xy[j+1][1]))
        if math.hypot(e.x-self.real_xy[i+1][0],e.y-self.real_xy[i+1][1])<35:self.real_dragging=i
    def real_drag(self,e):
        if self.real_dragging is None:return
        i=self.real_dragging;pts=self.coords(self.real_pulse,self.real_canvas,self.real_angles);x,y=pts[i]
        relative=math.degrees(math.atan2(e.y-y,e.x-x))-(-90+sum(self.real_angles[:i]))
        relative=(relative+180)%360-180;self.real_angles[i]=relative;self.draw_real()
    def real_release(self):
        if self.real_dragging is None:return
        i=self.real_dragging;self.real_dragging=None
        self.match_joint=i;self.match_pulse=self.real_pulse.copy();self.match_angles=self.real_angles.copy()
        try:self.finish_match();self.status.set('Observed joint '+str(i+1)+' saved at '+str(self.real_pulse[i])+'µs. Match another position to refine travel.')
        except Exception:
            self.cancel_match();raise
    def press(self,e):
        self.cancel_preview()
        if self.busy and not self.live_stream:return
        if self.range_edit.get():
            self.end_control()
            if hasattr(self,'range_handle') and math.hypot(e.x-self.range_handle[0],e.y-self.range_handle[1])<25:
                self.range_dragging=True;return
            if hasattr(self,'xy'):
                i=min(range(3),key=lambda j:math.hypot(e.x-self.xy[j][0],e.y-self.xy[j][1]))
                if math.hypot(e.x-self.xy[i][0],e.y-self.xy[i][1])<25:self.joint.set(['Lift','Middle','Head'][i]);self.draw()
            return
        self.start_control()
        self.preview_token+=1
        if hasattr(self,'xy'):
            near=min(range(3),key=lambda i:math.hypot(e.x-self.xy[i+1][0],e.y-self.xy[i+1][1]))
            if math.hypot(e.x-self.xy[near+1][0],e.y-self.xy[near+1][1])<35:self.dragging=near;self.joint.set(['Lift','Middle','Head'][near]);self.draw()
    def drag(self,e):
        if self.range_edit.get():
            if self.range_dragging:
                i=self.range_joint;pts=self.coords(self.pulse());x,y=pts[i]
                parent=-90+sum(interpolate(p,v) for p,v in zip(self.p['calibration'][:i],self.pulse()[:i]))
                angle=math.degrees(math.atan2(e.y-y,e.x-x))-parent
                angle+=360*round((self.range_center.get()-angle)/360)
                self.range_center.set(max(-540,min(540,angle)));self.draw()
            return
        if self.dragging is None or (self.busy and not self.live_stream):return
        i=self.dragging;pts=self.coords(self.pulse());x,y=pts[i];absolute=math.degrees(math.atan2(e.y-y,e.x-x))
        angles=self.match_angles if self.match_angles is not None else [interpolate(p,v) for p,v in zip(self.p['calibration'],self.pulse())]
        previous=-90+sum(angles[:i])
        relative=(absolute-previous+180)%360-180
        relative+=360*round((angles[i]-relative)/360)
        if self.match_angles is not None:
            selected=['Lift','Middle','Head'].index(self.joint.get())
            if i!=selected:return
            self.match_angles[i]=relative;self.draw();return
        value=round(interpolate(self.p['calibration'][i],relative,True));value=max(self.p['config']['low'][i],min(self.p['config']['high'][i],value));self.pulses[i].set(value);self.draw();self.attempt(self.publish_live)
    def send(self,kind,data=None):
        if self.busy:return
        if self.match_angles is not None:raise ValueError('Save or cancel picture matching before connecting or moving.')
        if self.range_edit.get():raise ValueError('Save or exit range editing before moving.')
        if self.previewing:raise ValueError('Stop or finish the screen preview before sending robot commands.')
        if kind!='connect' and not self.connected:raise ValueError('Connect board first.')
        self.preview_token+=1;self.busy=True;self.link.submit(kind,data)
    def ready(self):
        if not self.connected or not self.power.get():raise ValueError('Connect board and check external power/common ground first.')
        if self.busy:raise ValueError('Wait for completion or press STOP.')
    def base_row(self,d,hold=False):
        if self.base_reverse.get():d=-d
        speed=finite(float(self.base_speed.get()),1,100);neutral=int(self.base_neutral.get());base_command(d,speed,neutral)
        return dict(type='base',name='Base '+('reverse' if d<0 else 'forward'),direction=d,speed=speed,neutral=neutral,seconds=10 if hold else finite(float(self.base_seconds.get()),.1,10),hold=hold)
    def base_hold(self,d):
        self.ready();row=self.base_row(d,True)
        if self.match_angles is not None:raise ValueError('Finish picture matching first.')
        self.link.base_held=True;self.send('slump',([row],self.config(),self.count))
    def base_release(self):
        self.link.base_held=False
    def save_base_direction(self):
        self.p['base_reverse']=self.base_reverse.get();self.save()
    def save_roles(self):
        choices={key:v.get() for key,v in self.roles.items()}
        if any(name and name not in self.p['poses'] for name in choices.values()):raise ValueError('Choose existing checkpoints.')
        self.p['roles']=choices;self.save();self.status.set('Action checkpoints saved. No movement sent.')
    def load_action_starters(self):
        for role,key in [('Rest','upright'),('Slump','slump'),('Water','water'),('Stretch','stretch')]:
            name='Starter '+role
            if name not in self.p['poses']:
                values=self.p['config'][key].copy();values[2]=3000-values[2]
                check_pose(values,self.p['config']);self.p['poses'][name]=values
            self.roles[role].set(name)
        self.save_roles();self.refresh_lists();self.status.set('Starter checkpoints loaded. Estimates only: replace with poses observed on your lamp.')
    def action_rows(self,kind):
        rest=self.roles['Rest'].get();target=self.roles[kind].get()
        if rest not in self.p['poses'] or target not in self.p['poses']:raise ValueError('Select Rest and '+kind+' checkpoints, or load the editable starters.')
        return build_gesture(self.p,{key:var.get() for key,var in self.roles.items()},kind,self.action_style.get()=='Musical tones')
    def run_action(self,kind):
        self.ready();rows=self.action_rows(kind)
        if messagebox.askokcancel('Run '+kind,'Run '+kind+' using the selected checkpoints? Check clearance and support the lamp before first engagement.',parent=self.root):
            self.save_roles();self.send('slump',(rows,self.config(),self.count))
    def add_base(self,d):
        self.p['routine'].append(self.base_row(d));self.save();self.refresh_lists()
    def engage(self):self.attempt(self._engage)
    def _engage(self):
        self.ready();cfg=self.config();cfg['upright']=self.pulse()
        if messagebox.askokcancel('Support lamp','Engage at preview pulses '+str(cfg['upright'])+'? First engagement can jump. Support the lamp and check clearance.',parent=self.root):self.send('prepare',cfg)
    def row(self):return dict(name='Preview pose',pulse=self.pulse(),seconds=finite(float(self.seconds.get()),1,30),pause=0,sound=-1)
    def move(self):self.attempt(lambda:(self.ready(),self.send('slump',([self.row()],self.config(),self.count))))
    def use_current(self):
        if self.state and all(self.state['pulse'][:3]):
            for v,p in zip(self.pulses,self.state['pulse']):v.set(p)
            self.draw()
    def refresh_lists(self):
        if hasattr(self,'role_boxes'):
            for box in self.role_boxes:box.configure(values=list(self.p['poses']))
        self.poses.delete(0,'end')
        for name in self.p['poses']:self.poses.insert('end',name)
        self.rows.delete(0,'end')
        for i,r in enumerate(self.p['routine'],1):
            text=f"{i}. {r['name']} · {r['seconds']}s"
            text+=f" · {r['speed']}%" if r.get('type')=='base' else f" + {r['pause']}s · {SOUNDS[r['sound']+1]}"
            self.rows.insert('end',text)
    def selected(self):
        if not self.poses.curselection():raise ValueError('Select a saved checkpoint first.')
        return self.poses.get(self.poses.curselection()[0])
    def save_pose(self):self.attempt(self._save_pose)
    def _save_pose(self):
        name=simpledialog.askstring('Checkpoint','Name this preview pose:',parent=self.root)
        if not name:return
        if name in self.p['poses'] and not messagebox.askokcancel('Replace checkpoint',name+' already exists. Replace it?',parent=self.root):return
        self.p['poses'][name]=self.pulse();self.save();self.refresh_lists()
    def load_pose(self):self.attempt(self._load_pose)
    def _load_pose(self):
        self.preview_token+=1
        for v,p in zip(self.pulses,self.p['poses'][self.selected()]):v.set(p)
        self.draw()
    def delete_pose(self):self.attempt(lambda:(self.p['poses'].pop(self.selected()),self.save(),self.refresh_lists()))
    def reverse_joint(self):
        if self.busy or self.match_angles is not None:raise ValueError('Finish movement or picture matching first.')
        i=['Lift','Middle','Head'].index(self.joint.get())
        self.p['calibration'][i]=reverse_mapping(self.p['calibration'][i],self.pulse()[i])
        self.p['calibrated'][i]=False;self.p.setdefault('matches',{}).pop(str(i),None)
        self.save();self.cal_list();self.draw();self.match_text.set(self.joint.get()+' direction reversed. No robot movement sent.')
    def begin_match(self):
        if self.busy:raise ValueError('Wait until the robot stops first.')
        self.preview_token+=1
        if self.connected:
            if not self.state or self.state['active'][:3]!=[1,1,1] or any(self.state['moving'][:3]):raise ValueError('Engage the lamp and wait until it stops first.')
            self.use_current()
        self.match_pulse=self.pulse();self.match_angles=[interpolate(p,v) for p,v in zip(self.p['calibration'],self.match_pulse)]
        self.match_joint=['Lift','Middle','Head'].index(self.joint.get())
        self.match_text.set('Matching '+self.joint.get()+': drag its colored endpoint to match reality, then save. Robot movement is locked.')
        self.draw()
    def bend_match(self,amount):
        if self.match_angles is None:return self.status.set('Press Match picture first.')
        self.match_angles[self.match_joint]=max(-179,min(179,self.match_angles[self.match_joint]+amount));self.draw()
    def finish_match(self):
        if self.match_angles is None:raise ValueError('Start picture matching first.')
        i=self.match_joint;pulse=self.match_pulse[i];angle=self.match_angles[i]
        records=copy.deepcopy(self.p.get('matches',{}).get(str(i),[]))
        records=[r for r in records if r[0]!=pulse]+[[pulse,angle]]
        if self.p.get('full_ranges',[False]*3)[i]:
            delta=angle-interpolate(self.p['calibration'][i],pulse)
            points=[[p,a+delta] for p,a in self.p['calibration'][i]];checked=len(records)>=2
        elif len(records)>=2:
            mapping(records);points=sorted(records);checked=True
        else:
            delta=angle-interpolate(self.p['calibration'][i],pulse)
            points=[[p,a+delta] for p,a in self.p['calibration'][i]];checked=False
            if any(not -180<=a<=180 for p,a in points):
                slope=(points[-1][1]-points[0][1])/(points[-1][0]-points[0][0])
                points=[[pulse-1,angle-slope],[pulse+1,angle+slope]]
                points=[[max(500,min(2500,p)),max(-180,min(180,a))] for p,a in points];mapping(points)
        candidate=copy.deepcopy(self.p);candidate['calibration'][i]=points;candidate['calibrated'][i]=checked
        candidate.setdefault('matches',{})[str(i)]=records;check_project(candidate);self.p=candidate
        self.cancel_match();self.save();self.cal_list();self.draw()
        self.match_text.set('Saved '+str(len(records))+' matching position(s). '+('Direction and travel learned.' if checked else 'Now move this joint a little and match a second position.'))
    def cancel_match(self):
        self.match_angles=None;self.match_pulse=None;self.draw()
    def cal_list(self):
        if self.match_angles is not None and ['Lift','Middle','Head'].index(self.joint.get())!=self.match_joint:self.cancel_match()
        i=['Lift','Middle','Head'].index(self.joint.get());self.points.delete(0,'end')
        for p,a in self.p['calibration'][i]:self.points.insert('end',f'{p} µs → {a}°')
        self.confirmed.set(self.p['calibrated'][i])
        if self.range_edit.get():self.anchor_range(i)
        self.draw()
    def anchor_range(self,i):
        points=self.p['calibration'][i];pulse=self.pulse()[i];lo=self.p['config']['low'][i];hi=self.p['config']['high'][i]
        direction=1 if points[-1][1]>points[0][1] else -1
        self.range_center.set(interpolate(points,pulse)-direction*180*((pulse-lo)/(hi-lo)-.5))
    def open_range(self):
        self.range_edit.set(True);self.toggle_range()
        self.status.set('Rotate the white RANGE handle or use 5° buttons, then Save arc. Robot movement is locked.')
    def restore_range(self):
        self.open_range();self.save_range()
    def cancel_range(self):
        self.range_edit.set(False);self.range_dragging=False;self.draw();self.status.set('Arc editing cancelled. No changes applied.')
    def nudge_range(self,delta):
        if not self.range_edit.get():self.open_range()
        self.range_center.set(self.range_center.get()+delta);self.draw()
    def toggle_range(self):
        self.end_control();self.live_enabled.set(False);self.preview_token+=1
        if self.busy:self.range_edit.set(False);raise ValueError('Wait for movement to stop before editing the range.')
        if self.match_angles is not None:self.range_edit.set(False);raise ValueError('Finish picture matching first.')
        self.range_dragging=False;self.cal_list();self.draw()
    def draw_range(self,pts):
        if not hasattr(self,'joint'):return
        i=['Lift','Middle','Head'].index(self.joint.get());self.range_joint=i
        points=self.p['calibration'][i];lo=self.p['config']['low'][i];hi=self.p['config']['high'][i]
        a,b=interpolate(points,lo),interpolate(points,hi)
        if self.range_edit.get():
            proposed=full_range(points,self.range_center.get(),lo,hi);a,b=proposed[0][1],proposed[-1][1]
        parent=-90+sum(interpolate(p,v) for p,v in zip(self.p['calibration'][:i],self.pulse()[:i]));x,y=pts[i];radius=55
        arc=[]
        for n in range(41):
            angle=math.radians(parent+a+(b-a)*n/40);arc.extend((x+radius*math.cos(angle),y+radius*math.sin(angle)))
        self.canvas.create_line(*arc,fill=COLORS[i],width=3,dash=() if self.range_edit.get() else (4,3))
        for angle,pulse in ((a,lo),(b,hi)):
            r=math.radians(parent+angle);self.canvas.create_line(x,y,x+radius*math.cos(r),y+radius*math.sin(r),fill=COLORS[i],dash=(2,4))
            self.canvas.create_text(x+(radius+16)*math.cos(r),y+(radius+16)*math.sin(r),text=str(pulse),fill=COLORS[i],font=('Segoe UI',8))
        self.canvas.create_oval(x-5,y-5,x+5,y+5,fill='white')
        if self.range_edit.get():
            center=math.radians(parent+self.range_center.get());hx=x+radius*math.cos(center);hy=y+radius*math.sin(center);self.range_handle=(hx,hy)
            self.canvas.create_oval(hx-8,hy-8,hx+8,hy+8,fill='white',outline=COLORS[i]);self.canvas.create_text(hx,hy-15,text='RANGE',fill='white')
        if hasattr(self,'range_info'):self.range_info.set(f'{self.joint.get()} · {lo}–{hi}µs\nCurrent estimated span: {abs(interpolate(points,hi)-interpolate(points,lo)):.1f}°'+ ('\nEditing full 180° sector. Save to apply.' if self.range_edit.get() else '\nSelect Edit 180° range to expand or rotate it.'))
        self.range_summary.set(f"{self.joint.get()} · {'EDITING 180° — Save arc when aligned' if self.range_edit.get() else str(round(abs(interpolate(points,hi)-interpolate(points,lo)),1))+'° mapped'} · {lo}–{hi}µs")
    def save_range(self):
        if not self.range_edit.get():raise ValueError('Click Rotate arc first, or Use full 180° to restore the full range directly.')
        if self.busy:raise ValueError('Wait for motion to stop first.')
        i=self.range_joint;candidate=copy.deepcopy(self.p)
        candidate['calibration'][i]=full_range(candidate['calibration'][i],self.range_center.get(),candidate['config']['low'][i],candidate['config']['high'][i])
        candidate.setdefault('full_ranges',[False]*3)[i]=True;candidate['calibrated'][i]=False;candidate.setdefault('matches',{}).pop(str(i),None)
        check_project(candidate);self.p=candidate;self.save();self.range_edit.set(False);self.range_dragging=False;self.cal_list();self.draw()
        self.status.set(self.joint.get()+' full 180° visual range saved. No robot movement sent. Test clearance slowly.')
    def save_cal(self):self.attempt(self._save_cal)
    def _save_cal(self):
        i=['Lift','Middle','Head'].index(self.joint.get());pulse=self.pulse()[i];angle=finite(float(self.angle.get()),-180,180)
        points=[p for p in self.p['calibration'][i] if p[0]!=pulse]+[[pulse,angle]];mapping(points)
        self.p['calibration'][i]=sorted(points);self.p['calibrated'][i]=False;self.save();self.cal_list();self.draw()
    def remove_cal(self):self.attempt(self._remove_cal)
    def replace_cal(self):
        points=[[float(v.strip()) for v in item.split(',')] for item in self.pair.get().split(';')]
        if len(points)!=2 or any(len(point)!=2 for point in points):raise ValueError('Example: 1000,-30; 1600,30. Use angles you observed.')
        for pulse,angle in points:finite(pulse,500,2500);finite(angle,-180,180)
        mapping(points);i=['Lift','Middle','Head'].index(self.joint.get())
        self.p['calibration'][i]=sorted(points);self.p['calibrated'][i]=False;self.save();self.cal_list();self.draw()
    def _remove_cal(self):
        if not self.points.curselection():return
        i=['Lift','Middle','Head'].index(self.joint.get());pts=copy.deepcopy(self.p['calibration'][i]);pts.pop(self.points.curselection()[0]);mapping(pts)
        self.p['calibration'][i]=pts;self.p['calibrated'][i]=False;self.save();self.cal_list();self.draw()
    def confirm_cal(self):
        i=['Lift','Middle','Head'].index(self.joint.get());self.p['calibrated'][i]=self.confirmed.get();self.save();self.draw()
    def save_lengths(self):self.attempt(self._lengths)
    def _lengths(self):
        values=[finite(float(v.get()),10,500) for v in self.lengths];self.p['lengths']=values;self.save();self.draw()
    def append(self):self.attempt(self._append)
    def _append(self):
        name=self.selected();row=self.row();row.update(name=name,pulse=self.p['poses'][name].copy(),pause=finite(float(self.pause.get()),0,30),sound=SOUNDS.index(self.sound.get())-1)
        self.p['routine'].append(row);self.save();self.refresh_lists()
    def reorder(self,d):
        if not self.rows.curselection():return
        i=self.rows.curselection()[0];j=i+d
        if 0<=j<len(self.p['routine']):self.p['routine'][i],self.p['routine'][j]=self.p['routine'][j],self.p['routine'][i];self.save();self.refresh_lists();self.rows.selection_set(j)
    def remove_row(self):
        if self.rows.curselection():self.p['routine'].pop(self.rows.curselection()[0]);self.save();self.refresh_lists()
    def run(self):self.attempt(self._run)
    def _run(self):
        self.ready()
        if not self.p['routine']:raise ValueError('Append checkpoints first.')
        if messagebox.askokcancel('Run checkpoints','Run the saved checkpoints on the lamp? Check clearance along the entire path. STOP cancels the remaining routine.',parent=self.root):self.send('slump',(copy.deepcopy(self.p['routine']),self.config(),self.count))
    def cancel_preview(self):
        if self.previewing:
            self.preview_token+=1;self.previewing=False;self.preview_plan=None
            winsound.PlaySound(None,0)
    def preview(self,rows=None):self.attempt(lambda:self._preview(rows))
    def _preview(self,rows=None):
        if self.busy or self.match_angles is not None or self.range_edit.get():raise ValueError('Finish movement or calibration before previewing.')
        self.cancel_preview();self.end_control();self.live_enabled.set(False)
        rows=copy.deepcopy(self.p['routine'] if rows is None else rows)
        if not rows:raise ValueError('Add routine checkpoints first.')
        candidate=copy.deepcopy(self.p);candidate['routine']=rows;check_project(candidate)
        cfg=self.config();start=self.state['pulse'][:3].copy() if self.connected and self.state and self.state['active'][:3]==[1,1,1] else self.pulse()
        check_pose(start,cfg)
        self.preview_plan=dict(rows=rows,cfg=cfg,start=start,calibration=copy.deepcopy(self.p['calibration']),lengths=self.p['lengths'].copy(),head_face_sign=self.p.get('head_face_sign',1))
        if self.real_angles is None:self.real_reference=start.copy()
        self.previewing=True;self.preview_token+=1;token=self.preview_token
        estimate=0.;audio_end=0.;previous=start
        for row in rows:
            if row.get('type')=='base':estimate+=row['seconds'];continue
            eased=row.get('easing')=='quintic'
            if eased and row['sound']>=0:estimate=max(estimate,audio_end);audio_end=estimate+SOUND_SECONDS[row['sound']]
            estimate+=trajectory_duration(previous,row,cfg['max_speed']) if eased else preview_motion(previous,row['pulse'],row['seconds'],cfg['max_speed'],0)[1]
            if not eased and row['sound']>=0:estimate+=SOUND_SECONDS[row['sound']]
            estimate+=row['pause'];previous=row['pulse']
        estimate=max(estimate,audio_end);playback_begin=time.monotonic()
        def progress():
            if token!=self.preview_token:return
            elapsed=time.monotonic()-playback_begin
            self.playback_progress.set(min(100,100*elapsed/max(.1,estimate)))
            self.playback_text.set(f'Preview · {elapsed:.1f}s / approximately {estimate:.1f}s · no robot movement')
            if self.previewing:self.root.after(50,progress)
        progress()
        sound_until=[0.0]
        def play_cue(index):
            winsound.PlaySound(str(HERE/'sounds'/(SOUND_FILES[index]+'.wav')),winsound.SND_FILENAME|winsound.SND_ASYNC)
            sound_until[0]=time.monotonic()+SOUND_SECONDS[index]
        for var,value in zip(self.pulses,start):var.set(value)
        def next_row(index):
            if token!=self.preview_token:return
            if index>=len(rows):
                remaining=sound_until[0]-time.monotonic()
                if remaining>0:self.root.after(max(1,round(remaining*1000)),lambda:next_row(index));return
                self.previewing=False;self.playback_progress.set(100);self.playback_text.set('Preview complete · Run previewed plan uses the same gesture.');self.status.set('Preview complete. Run previewed plan uses this same motion, pauses and sounds.');return
            row=rows[index];initial=self.pulse();begin=time.monotonic();self.status.set('SCREEN ONLY · '+row['name'])
            if row.get('type')=='base':
                self.base_status.set('Preview: '+row['name']+f" for {row['seconds']}s · heading unknown")
                self.root.after(round(row['seconds']*1000),lambda:next_row(index+1));return
            eased=row.get('easing')=='quintic'
            if eased and row['sound']>=0:
                remaining=sound_until[0]-time.monotonic()
                if remaining>0:self.root.after(max(1,round(remaining*1000)),lambda:next_row(index));return
                play_cue(row['sound'])
            def arrived():
                if token!=self.preview_token:return
                sound=row['sound'];seconds=0
                if sound>=0 and not eased:
                    seconds=SOUND_SECONDS[sound]
                    play_cue(sound)
                    self.status.set('SCREEN ONLY · '+row['name']+' · '+SOUNDS[sound+1])
                self.root.after(round(1000*(seconds+row['pause'])),lambda:next_row(index+1))
            def tick():
                if token!=self.preview_token:return
                pose,duration=sample_motion(initial,row,time.monotonic()-begin,cfg['max_speed']) if eased else preview_motion(initial,row['pulse'],row['seconds'],cfg['max_speed'],time.monotonic()-begin)
                for var,value in zip(self.pulses,pose):var.set(value)
                self.draw()
                if time.monotonic()-begin<duration:self.root.after(30,tick)
                else:arrived()
            tick()
        next_row(0)
    def run_previewed(self):
        self.ready()
        if self.previewing:raise ValueError('Wait for the preview to finish first.')
        plan=self.preview_plan
        if not plan:raise ValueError('Preview a complete action or routine first.')
        if plan['calibration']!=self.p['calibration'] or plan['lengths']!=self.p['lengths'] or plan.get('head_face_sign',1)!=self.p.get('head_face_sign',1):raise ValueError('The lamp model changed. Preview again before running.')
        if not self.state or self.state['active'][:3]!=[1,1,1] or self.state['pulse'][:3]!=plan['start']:raise ValueError('The robot starting pose differs from the preview. Preview again from its current position.')
        if messagebox.askokcancel('Run previewed plan','Run exactly the previewed checkpoints, speed limit, pauses and sounds? Physical clearance still needs checking.',parent=self.root):
            self.send('slump',(copy.deepcopy(plan['rows']),copy.deepcopy(plan['cfg']),self.count))
    def stop(self):
        self.cancel_preview()
        self.end_control();self.live_enabled.set(False)
        self.base_release()
        self.preview_token+=1
        if self.connected:self.busy=True;self.link.submit('stop')
        self.status.set('Stopped. Remaining routine cancelled.')
    def release(self):
        self.cancel_preview()
        self.end_control();self.live_enabled.set(False)
        self.preview_token+=1
        if self.connected and messagebox.askokcancel('Support lamp','Release signals? Support the lamp so it cannot fall.',parent=self.root):self.busy=True;self.link.submit('off')
    def close(self):
        self.cancel_preview()
        self.end_control()
        if self.connected:
            if not messagebox.askokcancel('Close controller','Closing releases signals. Support the lamp first.',parent=self.root):return
            self.closing=True;self.auto_connect.set(False)
            self.preview_token+=1;self.link.submit('close')
        else:self.root.destroy()
    def disconnect_board(self):
        if self.busy:messagebox.showinfo('Wait','Stop the current operation first.',parent=self.root);return
        if self.connected:
            if not messagebox.askokcancel('Disconnect','Support the lamp. Disconnecting releases its outputs.',parent=self.root):return
            self.cancel_preview();self.end_control();self.live_enabled.set(False);self.auto_connect.set(False);self.disconnecting=True;self.busy=True;self.link.submit('close')
        else:self.auto_connect.set(False);self.status.set('Automatic reconnection paused. You can load profiles or preview offline.')
    def retry_connection(self):
        now=time.monotonic()
        if self.closing or self.disconnecting or self.connected or self.busy or not self.auto_connect.get() or now<self.retry_at:return
        self.retry_at=now+min(10,1.5*2**min(self.retry_count,3))
        if self.previewing or self.range_edit.get() or self.match_angles is not None:return
        try:board_port()
        except Exception:
            self.connection.set('Waiting for board USB…');return
        self.connection.set('Reconnecting USB…');self.send('connect')
    def poll(self):
        self.link.ui_alive=time.monotonic()
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='connected':
                    self.connected=True;self.busy=False;self.count=data[1];self.retry_count=0;self.connection.set(f'{data[0]} · {self.count} sounds ready')
                    self.live_enabled.set(False);self.status.set('USB connected. Movement will not resume automatically; engage the supported lamp when ready.')
                elif kind=='state':
                    self.state=data;self.draw()
                    self.base_status.set(('Turning · ' if data['base_spin'] else 'Stopped · ')+f"command {data['pulse'][3]}µs · heading unknown")
                elif kind=='phase':self.status.set(data)
                elif kind=='finished':
                    was_live=self.live_stream;self.busy=False;self.live_stream=False;self.status.set(data)
                    if was_live:self.end_control();self.use_current()
                elif kind=='error':
                    self.connected=False;self.busy=False;self.live_stream=False;self.live_enabled.set(False);self.end_control();self.base_release();self.power.set(False);self.state=None;self.preview_plan=None
                    self.retry_count+=1;self.retry_at=time.monotonic()+min(10,1.5*2**min(self.retry_count-1,3));self.connection.set('Disconnected · retry scheduled' if self.auto_connect.get() else 'Disconnected');self.status.set(data)
                elif kind=='closed':
                    if self.disconnecting:
                        self.disconnecting=False;self.connected=False;self.busy=False;self.state=None;self.power.set(False);self.connection.set('Offline · auto reconnect paused')
                        self.link=VisualLink(lambda *e:self.events.put(e));continue
                    self.root.destroy();return
        except queue.Empty:pass
        self.retry_connection();self.root.after(50,self.poll)

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
