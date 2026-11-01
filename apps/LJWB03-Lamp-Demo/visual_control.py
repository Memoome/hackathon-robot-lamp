"""Calibrated side-view pose editor. Drawing is an estimate; automatic Stretch requires explicit visual-interaction enablement."""
import copy,json,math,pathlib,queue,re,time,tkinter as tk
import winsound
import threading, urllib.request
from visual_interaction import VisualActionTrigger, PresenceLight, visible_person
from tkinter import ttk,messagebox,simpledialog,colorchooser
from lamp_demo import LampLink,DEFAULT,validate,Cancelled,board_port
from live_control import base_command
from expressive_routines import build_gesture,build_sad,build_happy,sad_light,emotion_light,sample_emotion_light,sample_motion,trajectory_duration,coordinated_row
HERE=pathlib.Path(__file__).resolve().parent
FILE=HERE/'visual-lamp.json'
PROFILES=HERE/'profiles'
SOUND_FILES=['robot_slump','robot_recover','music_slump','music_recover','robot_water','music_water','robot_stretch','music_stretch','robot_chuckle','robot_stretch_ahh']
SOUND_SECONDS=[2.1,1.6,2.1,1.6,2.3,2.3,2.3,2.3,1.45,1.65]
COLORS=('#36b8bd','#f6b85a','#a89aed')
SOUNDS=['None','Robot slump','Robot happy','Music slump','Music happy','Robot water','Music water','Robot stretch','Music stretch','Cheeky chuckle','Stretch ahhh']
SERVO_WIRING=('Current lamp motors (31 October 2026)\n\n'
    'Joint 1 / lift: MG996R position servo → GPIO12\n'
    'Joint 2 / elbow: MG90S position servo → GPIO10\n'
    'Joint 3 / head: SG90 position servo → GPIO11\n'
    'Base: SG90 position servo → GPIO15\n\n'
    'All use the existing 50Hz control signal. Base position controls set an estimated angle.\n'
    'Red wires → regulated external 5V. Brown/black → supply GND; join supply GND to board GND. '
    'Keep external +5V separate from the USB-powered board +5V.\n\n'
    'The available 500–2500µs controls are not certified mechanical endpoints for a new servo. '
    'For the new lift, begin unloaded/supported around 1500µs, explore 1000–2000µs first, '
    'then expand gradually only while movement remains free. Stop if it binds or buzzes.\n\n'
    'Replacing a servo or refitting its horn changes the pulse-to-lamp alignment. '
    'Match the observed drawing again and check poses before running the old routines. '
    'The full-180° drawing is an estimate, not a measured specification.\n\n'
    'The base now uses SG90 position control. Timed continuous-base steps are blocked. '
    'Use Rotating base to preview and save position checkpoints.')

def finite(x,lo,hi):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not lo<=x<=hi:raise ValueError(f'Use a number within {lo}..{hi}.')
    return x

def without_base_motion(rows):
    result=copy.deepcopy(rows)
    result=[row for row in result if row.get('type') not in ('base','base_position')]
    for row in result:row.pop('base_pulse',None)
    return result

def led_rgb(colour,brightness):
    if not isinstance(colour,str) or len(colour)!=7 or colour[0]!='#':raise ValueError('Choose a colour in #RRGGBB format.')
    try:rgb=[int(colour[n:n+2],16) for n in (1,3,5)]
    except ValueError:raise ValueError('Choose a colour in #RRGGBB format.')
    finite(brightness,0,100)
    return [round(x*brightness/100) for x in rgb]

def validate_row_light(row):
    if 'light_rgb' in row:
        rgb=row['light_rgb']
        if not isinstance(rgb,list) or len(rgb)!=3 or any(type(x)!=int or not 0<=x<=255 for x in rgb):raise ValueError('Invalid routine RGB colour.')
    if 'light_breathe' in row:finite(row['light_breathe'],1,4)

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
                calibration=[[[500,-90],[2500,90]],[[500,90],[2500,-90]],[[500,90],[2500,-90]]],
                calibrated=[False]*3,poses={},routine=[],base_reverse=True,direction_fix_20261030=True,
                head_mount_direction_fix_20261031=True,elbow_mount_direction_fix_20261031=True,
                head_up_direction_fix_20261031=True)
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
    if not p.get('head_mount_direction_fix_20261031'):
        # The actual lamp's head linkage reverses the shaft direction. Keep
        # the current picture fixed while reversing both forward/inverse maps.
        anchor=p.get('preview_pulse',p['config']['start'])[2]
        p['calibration'][2]=reverse_mapping(p['calibration'][2],anchor)
        p.setdefault('matches',{}).pop('2',None)
        p['head_mount_direction_fix_20261031']=True
    if not p.get('elbow_mount_direction_fix_20261031'):
        anchor=p.get('preview_pulse',p['config']['start'])[1]
        p['calibration'][1]=reverse_mapping(p['calibration'][1],anchor)
        p.setdefault('matches',{}).pop('1',None)
        p['elbow_mount_direction_fix_20261031']=True
    if not p.get('head_up_direction_fix_20261031'):
        # User verified elbow, then observed that head up/down is reversed.
        anchor=p.get('preview_pulse',p['config']['start'])[2]
        p['calibration'][2]=reverse_mapping(p['calibration'][2],anchor)
        p.setdefault('matches',{}).pop('2',None)
        p['head_up_direction_fix_20261031']=True
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
        validate_row_light(row)
        if 'warm_level' in row:finite(row['warm_level'],0,1)
        if 'light_progress' in row:finite(row['light_progress'],0,1)
        if 'base_pulse' in row:
            finite(row['base_pulse'],500,2500)
            if type(row['base_pulse'])!=int:raise ValueError('Invalid coordinated base pulse.')
        if row.get('type')=='base_position':position_base_row(row);continue
        if row.get('type')=='base':
            base_command(row['direction'],row['speed'],row['neutral']);finite(row['seconds'],.1,10)
            continue
        check_pose(row['pulse'],p['config']);finite(row['seconds'],.1 if row.get('easing')=='quintic' else 1,30);finite(row['pause'],0,30)
        if row.get('easing')=='quintic':
            if len(row.get('delays',[]))!=3:raise ValueError('Expected three joint timing offsets.')
            for delay in row['delays']:finite(delay,0,.4)
        if type(row['sound'])!=int or not -1<=row['sound']<=9:raise ValueError('Invalid sound.')
    return p

def check_pose(pulse,cfg):
    if len(pulse)!=3 or any(type(v)!=int or not lo<=v<=hi for v,lo,hi in zip(pulse,cfg['low'],cfg['high'])):raise ValueError('Pose outside saved pulse limits.')

def position_base_row(row):
    if row.get('type')!='base_position':raise ValueError('Old timed continuous-base turns cannot run with the SG90. Remove them and add position checkpoints.')
    finite(row['pulse'],500,2500);finite(row['seconds'],.2,30)
    if type(row['pulse'])!=int:raise ValueError('Base pulse must be an integer.')
    return row

def base_angle(pulse,reverse=False):
    angle=(pulse-500)*180/2000
    return 180-angle if reverse else angle

def base_motion_duration(start,row):
    distance=abs(row['pulse']-start)
    speed=max(10,min(600,round(distance/row['seconds'])))
    return distance/speed if distance else 0

class VisualLink(LampLink):
    def idle(self):
        context=getattr(self,'presence_light_context',None)
        if context is None:return
        enabled,present,expires=context
        now=time.monotonic()
        if not hasattr(self,'presence_light'):self.presence_light=PresenceLight()
        rgb=self.presence_light.rgb(enabled and present and now<=expires,now)
        # Actions can change the ring; restore the presence light after they finish.
        if rgb!=getattr(self,'presence_light_last',None) or getattr(self,'presence_light_dirty',True):
            raw=self.exchange('lamp_led set '+' '.join(map(str,rgb)),rb'LED_(?:STATUS|ERROR)[^\r\n]*')
            if b'LED_ERROR' in raw:raise RuntimeError('Presence light update failed.')
            self.presence_light_last=rgb;self.presence_light_dirty=False
            self.emit('emotion_light',rgb)
        if not enabled:self.presence_light_context=None
    def led(self,data):
        self.presence_light_dirty=True
        super().led(data)
    def perform(self,kind,payload):
        self.presence_light_dirty=True
        if isinstance(payload,dict) and payload.get('base_live'):
            self.live_base();self.emit('finished','Base drag stopped at current commanded position.');return
        if isinstance(payload,dict) and 'base_position' in payload:
            self.position_base(payload['base_position'],payload.get('engage',False));self.emit('finished','Base at commanded pulse; physical angle is estimated.');return
        if isinstance(payload,dict) and payload.get('live'):
            self.live_drag(payload['cfg']);return
        rows,cfg,count=payload
        validate(cfg)
        for row in rows:
            validate_row_light(row)
            if 'warm_level' in row:finite(row['warm_level'],0,1)
            if 'light_progress' in row:finite(row['light_progress'],0,1)
            if 'base_pulse' in row:
                finite(row['base_pulse'],500,2500)
                if type(row['base_pulse'])!=int:raise ValueError('Invalid coordinated base pulse.')
            if row.get('type')=='base_position':position_base_row(row);continue
            if row.get('type')=='base':
                raise ValueError('Replace old continuous-base rows with SG90 position checkpoints.')
            check_pose(row['pulse'],cfg);finite(row['seconds'],.1 if row.get('easing')=='quintic' else 1,30);finite(row['pause'],0,30)
            if row['sound']>=count:raise ValueError('Board firmware does not include the selected sound.')
        self.exchange('arm_live status')
        if any('light_progress' in row or 'warm_level' in row or 'light_rgb' in row for row in rows):
            raw=self.exchange('lamp_led status',rb'LED_(?:STATUS|ERROR)[^\r\n]*')
            match=re.search(rb'LED_STATUS[^\r\n]* r=(\d+) g=(\d+) b=(\d+)',raw)
            if not match:raise ValueError('LED ring control is unavailable; emotion was not started.')
            self.light_origin=list(map(int,match.groups()));self.light_current=self.light_origin.copy()
            self.emit('emotion_light',self.light_origin.copy())
        if cfg.get('run_engage'):
            start=cfg['run_start'];check_pose(start,cfg);finite(cfg['run_base_start'],500,2500)
            if any(row.get('type')!='base_position' for row in rows):
                for i,pin in enumerate((12,10,11)):
                    self.check()
                    if not self.state['active'][i]:self.exchange(f'arm_live engage {pin} {start[i]} 1')
            if any('base_pulse' in row or row.get('type')=='base_position' for row in rows) and not self.state['active'][3]:
                base=cfg['run_base_start'];finite(base,500,2500);self.check()
                self.exchange(f'arm_live engage 15 {base} 1')
        if any(row.get('type')=='base_position' or 'base_pulse' in row for row in rows) and not self.state['active'][3]:raise ValueError('Engage the SG90 base first before running this action.')
        if any(row.get('type') not in ('base','base_position') for row in rows) and (self.state['active'][:3]!=[1,1,1] or self.state['base_spin']):raise ValueError('Set the initial pose first and keep the base stopped.')
        pending=None
        for n,row in enumerate(rows,1):
            self.performance_context=(n,len(rows))
            self.emit('run_phase',dict(index=n,total=len(rows),name=row['name'],pulse=row.get('pulse'),base=row.get('base_pulse',row.get('pulse') if row.get('type')=='base_position' else None)))
            self.report_run_progress(0)
            self.check();self.emit('phase',f"Checkpoint {n}/{len(rows)} · {row['name']}")
            if row.get('type')=='base_position':self.position_base(row);continue
            if row.get('type')=='base':
                self.turn_base(row);continue
            if row.get('easing')=='quintic':
                if row['sound']>=0:
                    if pending is not None:self.finish_sound(pending)
                    self.start_sound(row['sound'],cfg['volume']);pending=row['sound']
                self.expressive_glide(row,cfg);self.hold_pause(row['pause']);self.report_run_progress(1);continue
            self.glide(row['pulse'],row['seconds'],cfg)
            if row['sound']>=0:
                self.start_sound(row['sound'],cfg['volume']);self.finish_sound(row['sound'])
            self.hold_pause(row['pause'])
            self.report_run_progress(1)
        if pending is not None:self.finish_sound(pending)
        self.emit('run_complete',None);self.performance_context=None
        self.emit('finished','Done. Last commanded pose is holding.')
    def report_run_progress(self,fraction):
        context=getattr(self,'performance_context',None)
        if context:
            index,total=context;self.emit('run_progress',min(99,100*(index-1+max(0,min(1,fraction)))/total))
    def start_sound(self,index,volume):
        self.emit('run_sound',(index,'requesting'))
        super().start_sound(index,volume)
        state,selected=self.emotion_status()
        if selected!=index or state not in (1,2):raise RuntimeError('Speaker rejected the sound cue.')
        self.emit('run_sound',(index,'accepted by board'))
    def finish_sound(self,index):
        super().finish_sound(index);self.emit('run_sound',(index,'completed'))
    def expressive_glide(self,row,cfg):
        start=self.state['pulse'][:3].copy()
        base_start=self.state['pulse'][3] if 'base_pulse' in row else 1500
        row=coordinated_row(start,row,cfg['max_speed'],base_start)
        duration=trajectory_duration(start,row,cfg['max_speed'])
        base_speed=max(10,min(600,round(abs(row.get('base_pulse',base_start)-base_start)/max(.1,duration))))
        begin=time.monotonic()
        light_start=getattr(self,'light_current',[0,0,0]).copy();light_last=-1
        while True:
            self.check();pose,duration=sample_motion(start,row,time.monotonic()-begin,cfg['max_speed'])
            if ('light_progress' in row or 'warm_level' in row or 'light_rgb' in row) and time.monotonic()-begin-light_last>=.12:
                rgb=sample_emotion_light(self.light_origin,row,light_start,(time.monotonic()-begin)/duration)
                self.set_emotion_light(rgb);light_last=time.monotonic()-begin
            if 'base_pulse' in row:self.command_base_target(row['base_pulse'],base_speed)
            self.exchange('arm_live glide '+' '.join(map(str,(*pose,cfg['max_speed']))))
            self.report_run_progress(.9*min(1,(time.monotonic()-begin)/duration))
            if time.monotonic()-begin>=duration:break
            self.wait_until(time.monotonic()+.05)
        # Account for transport lag without jumping to an unacknowledged target.
        self.glide(row['pulse'],.2,cfg)
        if 'light_progress' in row or 'warm_level' in row or 'light_rgb' in row:self.set_emotion_light(emotion_light(self.light_origin,row))
        if 'base_pulse' in row:
            deadline=time.monotonic()+3
            while self.state['pulse'][3]!=row['base_pulse']:
                self.check();self.command_base_target(row['base_pulse'],base_speed)
                if time.monotonic()>deadline:raise RuntimeError('Base did not finish; next gesture cancelled.')
                self.wait_until(time.monotonic()+.05)
    def command_base_target(self,target,speed):
        current=self.state['pulse'][3]
        if current!=target:self.exchange(f'arm_live target 15 {target} {speed}')
    def set_emotion_light(self,rgb):
        self.check()
        if rgb!=self.light_current:
            raw=self.exchange('lamp_led set '+' '.join(map(str,rgb)),rb'LED_(?:STATUS|ERROR)[^\r\n]*')
            if b'LED_ERROR' in raw:raise RuntimeError('LED fade failed; action stopped.')
            self.light_current=rgb.copy();self.emit('emotion_light',rgb)
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
        raise ValueError('Timed continuous-base commands are disabled for the SG90.')
    def position_base(self,row,engage=False):
        position_base_row(row);self.check();self.exchange('arm_live status')
        target=row['pulse']
        if engage:
            self.exchange(f'arm_live engage 15 {target} 1')
        else:
            if not self.state['active'][3] or self.state['base_spin']:raise ValueError('Engage the SG90 base first in Rotating base.')
            start=self.state['pulse'][3];speed=max(10,min(600,round(abs(target-start)/row['seconds'])))
            deadline=time.monotonic()+abs(target-start)/speed+3
            try:
                while self.state['pulse'][3]!=target:
                    self.check()
                    self.exchange(f'arm_live target 15 {target} {speed}')
                    if time.monotonic()>deadline:raise RuntimeError('Base move timed out.')
                    self.wait_until(time.monotonic()+.05)
                    self.report_run_progress(.9*(1-abs(target-self.state['pulse'][3])/max(1,abs(target-start))))
            finally:self.exchange('arm_live freeze')
    def live_base(self):
        self.check();self.exchange('arm_live status')
        if not self.state['active'][3] or self.state['base_spin']:raise ValueError('Engage the SG90 base first.')
        try:
            while self.base_live_held:
                self.check();target,speed,updated=self.base_live_target
                if time.monotonic()-updated>.3:break
                finite(target,500,2500);finite(speed,10,600)
                current=self.state['pulse'][3]
                if current!=target:
                    self.exchange(f'arm_live target 15 {target} {speed}')
                else:self.exchange('arm_live freeze')
                self.wait_until(time.monotonic()+.05)
        finally:self.exchange('arm_live freeze')

class App:
    def __init__(self,root):
        self.root=root;self.p=fresh();self.events=queue.Queue();self.state=None;self.connected=False;self.busy=False;self.count=0;self.dragging=None;self.preview_token=0;self.match_angles=None;self.match_pulse=None
        self.live_stream=False;self.control_held=False;self.last_live=None;self.real_angles=None;self.real_dragging=None
        self.previewing=False;self.preview_plan=None;self.performance_active=False;self.performance_target=None;self.performance_base_target=None
        self.real_reference=None
        self.visual_trigger=VisualActionTrigger();self.visual_fetching=False;self.visual_next=0
        self.visual_enabled=tk.BooleanVar(value=False)
        self.visual_generation=0
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
        ttk.Checkbutton(top,text='Auto reconnect',variable=self.auto_connect).pack(side='right',padx=5)
        ttk.Button(top,text='Wireless setup',command=self.open_wireless_setup).pack(side='right',padx=5)
        interactionbar=ttk.Frame(root,padding=(12,0,12,4));interactionbar.pack(fill='x')
        ttk.Checkbutton(interactionbar,text='视觉联动：见人呼吸灯 · 久坐喝水 · 低头伸展',variable=self.visual_enabled,command=self.toggle_visual_interaction).pack(side='left')
        self.visual_status=tk.StringVar(value='未启用 · 先连接并启用四个关节；视觉服务需运行')
        ttk.Label(interactionbar,textvariable=self.visual_status).pack(side='left',padx=8)
        profilebar=ttk.Frame(root,padding=(12,0,12,6));profilebar.pack(fill='x')
        self.profile_name=tk.StringVar(value=self.p.get('profile_name','Lamp Cardboard Prototype'))
        self.profile_box=ttk.Combobox(profilebar,textvariable=self.profile_name,width=28);self.profile_box.pack(side='left')
        ttk.Button(profilebar,text='Save profile',command=lambda:self.attempt(self.save_profile)).pack(side='left',padx=5)
        ttk.Button(profilebar,text='Load profile',command=lambda:self.attempt(self.load_profile)).pack(side='left',padx=5)
        ttk.Button(profilebar,text='Servo wiring',command=lambda:messagebox.showinfo('Lamp motors & wiring',SERVO_WIRING,parent=root)).pack(side='left',padx=5)
        ttk.Button(profilebar,text='▶ Run previewed plan',command=lambda:self.attempt(self.run_previewed)).pack(side='right')
        # Reserve the stop bar before the expanding canvases, including on smaller screens.
        bottom=ttk.Frame(root,padding=8);bottom.pack(side='bottom',fill='x')
        ttk.Button(bottom,text='STOP motion + sound + preview',command=self.stop).pack(side='left')
        ttk.Button(bottom,text='Release outputs…',command=self.release).pack(side='left',padx=8)
        ttk.Label(bottom,textvariable=self.status,wraplength=650).pack(side='left',padx=10)
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
        self.live_enabled=tk.BooleanVar();ttk.Label(left,text='Live dragging is automatic once the three arm joints are engaged.').pack(anchor='w',pady=3)
        self.live_max=tk.StringVar(value='600');self.field(left,'Live speed limit (µs/s, 10–600)',self.live_max)
        ttk.Label(left,text='OBSERVED ARM · adjust to match the real lamp',font=('Segoe UI',11,'bold')).pack(anchor='w')
        self.real_canvas=tk.Canvas(left,bg='#25343b',highlightthickness=0,width=490,height=230);self.real_canvas.pack(fill='both',expand=True)
        self.real_canvas.bind('<Configure>',lambda e:self.draw_real());self.real_canvas.bind('<Button-1>',lambda e:self.attempt(lambda:self.real_press(e)))
        self.real_canvas.bind('<B1-Motion>',self.real_drag);self.real_canvas.bind('<ButtonRelease-1>',lambda e:self.attempt(self.real_release))
        ttk.Label(left,text='Top: estimated command. Bottom: your observation, saved as calibration.\nNo position sensors. Live speed follows your drag, capped at600µs/s.',wraplength=490).pack(pady=4)
        self.pulses=[]
        for i,name in enumerate(('Lift MG996R · GPIO12','Elbow MG90S · GPIO10','Head SG90 · GPIO11')):
            row=ttk.Frame(left);row.pack(fill='x',pady=3);ttk.Label(row,text=name,width=22).pack(side='left')
            v=tk.DoubleVar(value=self.p.get('preview_pulse',self.p['config']['start'])[i]);self.pulses.append(v)
            slider=ttk.Scale(row,from_=self.p['config']['low'][i],to=self.p['config']['high'][i],variable=v,command=lambda _,j=i:self.slider_changed());slider.pack(side='left',fill='x',expand=True)
            slider.bind('<ButtonPress-1>',lambda e:self.start_control(),add='+');slider.bind('<ButtonRelease-1>',lambda e:self.end_control(),add='+')
            slider.bind('<Leave>',lambda e:self.end_control(),add='+')
            ent=ttk.Entry(row,textvariable=v,width=8);ent.pack(side='left',padx=5);ent.bind('<Return>',lambda e:self.draw())
        tabs=ttk.Notebook(right);tabs.pack(fill='both',expand=True)
        pose=ttk.Frame(tabs,padding=10);cal=ttk.Frame(tabs,padding=10);routine=ttk.Frame(tabs,padding=10);base=ttk.Frame(tabs,padding=10)
        tabs.add(pose,text='Pose control');tabs.add(cal,text='Calibrate drawing');tabs.add(routine,text='Routine')
        tabs.add(base,text='Rotating base')
        led=ttk.Frame(tabs,padding=10);tabs.add(led,text='LED ring')
        ttk.Label(led,text='LED ring · 8 lights · GPIO1',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=8)
        ttk.Label(led,text='Choose a colour and brightness, then press Apply.\nThis controls the whole ring. Servo settings are unchanged.',wraplength=450).pack(anchor='w',pady=5)
        self.led_colour=tk.StringVar(value='#FFD59A');self.led_brightness=tk.DoubleVar(value=10);self.led_power=tk.BooleanVar(value=True)
        self.led_sample=tk.Label(led,text='Colour preview',bg=self.led_colour.get(),fg='#111111',height=3);self.led_sample.pack(fill='x',pady=8)
        presets=ttk.Frame(led);presets.pack(fill='x')
        for name,colour in [('Warm','#FFD59A'),('White','#FFFFFF'),('Red','#FF0000'),('Green','#00FF00'),('Blue','#0000FF')]:
            ttk.Button(presets,text=name,command=lambda c=colour:self.set_led_colour(c)).pack(side='left',expand=True,fill='x')
        ttk.Button(led,text='Choose another colour…',command=self.choose_led_colour).pack(fill='x',pady=6)
        self.led_level=tk.StringVar(value='Brightness: 10%')
        ttk.Label(led,textvariable=self.led_level).pack(anchor='w')
        ttk.Scale(led,from_=0,to=100,variable=self.led_brightness,command=lambda _:self.led_level.set(f'Brightness: {round(self.led_brightness.get())}%')).pack(fill='x',pady=8)
        ttk.Label(led,text='External 5V and common ground already confirmed.').pack(anchor='w',pady=8)
        ttk.Button(led,text='Apply colour',command=lambda:self.attempt(self.apply_led)).pack(fill='x',pady=5)
        ttk.Button(led,text='LEDs OFF',command=lambda:self.attempt(lambda:self.apply_led(off=True))).pack(fill='x',pady=5)
        ttk.Label(led,text='DI → GPIO1 data path; DO unconnected. Use the recommended\nlevel shifter and 330Ω series resistor at DI.\nApply and OFF change lights only; they do not move servos.\nLights retain their last colour if USB disconnects; use OFF before unplugging.',wraplength=450).pack(anchor='w',pady=12)
        test=ttk.Frame(tabs,padding=10);tabs.insert(0,test,text='Servo test')
        tabs.insert(1,led)
        ttk.Label(test,text='Orient one servo at a time',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(test,text='1. Support / unload the lamp.\n2. Apply 1500µs to ONE joint, then fit its horn.\n3. Use small steps to check its free travel.\nFull software bounds: 500–2500µs; physical stops may be narrower.',wraplength=450).pack(anchor='w',pady=6)
        self.test_pulses=[];self.test_states=[];self.test_step=tk.StringVar(value='10')
        self.field(test,'Step size (µs, 1–2000)',self.test_step)
        for i,name in enumerate(('Lift MG996R · GPIO12','Elbow MG90S · GPIO10','Head SG90 · GPIO11')):
            card=ttk.LabelFrame(test,text=name,padding=5);card.pack(fill='x',pady=4)
            value=tk.StringVar(value='1500');self.test_pulses.append(value)
            row=ttk.Frame(card);row.pack(fill='x')
            ttk.Entry(row,textvariable=value,width=8).pack(side='left')
            ttk.Label(row,text='µs').pack(side='left',padx=3)
            ttk.Button(row,text='Apply pulse…',command=lambda j=i:self.attempt(lambda:self.test_apply(j))).pack(side='left',padx=3)
            for label,d in [('− Step',-1),('+ Step',1)]:
                ttk.Button(row,text=label,command=lambda j=i,d=d:self.attempt(lambda:self.test_nudge(j,d))).pack(side='left',padx=2)
            state=tk.StringVar(value='Released · physical position unknown');self.test_states.append(state)
            ttk.Label(card,textvariable=state).pack(anchor='w')
        ttk.Label(test,text='Steps start at the last board command, not the edited input.\nOnly the selected joint changes; other outputs keep their state.\nBegin the new lift within 1000–2000µs. Stop on binding/buzzing.\nBase SG90 position: use the Rotating base tab.',wraplength=450).pack(anchor='w',pady=6)
        ttk.Label(base,text='Base SG90 · position · GPIO15',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=5)
        ttk.Label(base,text='Drag the pointer or slider to move the engaged base live.\nRelease the mouse to stop. Before engagement, dragging is preview only.\nAngles assume 180° travel; verify the actual servo and clearance.',wraplength=460).pack(anchor='w')
        settings=self.p.get('base_position',{})
        self.base_target=tk.DoubleVar(value=settings.get('preview',1500))
        self.base_control_held=False;self.base_stream=False;self.base_drag_previous=None;self.link.base_live_held=False
        self.base_speed=tk.StringVar(value='5');self.base_neutral=tk.StringVar(value='1500');self.base_seconds=tk.StringVar(value='2')
        self.base_reverse=tk.BooleanVar(value=settings.get('reverse',False))
        self.base_front=float(settings.get('front',90))
        self.water_angle=tk.StringVar(value=str(settings.get('water_angle',self.base_front+90 if self.base_front<=90 else self.base_front-90)))
        self.base_canvas=tk.Canvas(base,bg='#12232e',height=210,highlightthickness=0);self.base_canvas.pack(fill='x',pady=4)
        self.base_canvas.bind('<Configure>',lambda e:self.draw_base())
        self.base_canvas.bind('<Button-1>',self.base_point);self.base_canvas.bind('<B1-Motion>',self.base_point)
        base_slider=ttk.Scale(base,from_=500,to=2500,variable=self.base_target,command=lambda _:self.draw_base());base_slider.pack(fill='x')
        base_slider.bind('<ButtonPress-1>',lambda e:self.start_base_drag(),add='+')
        for widget in (base_slider,self.base_canvas):
            widget.bind('<ButtonRelease-1>',lambda e:self.base_release(),add='+')
            widget.bind('<Leave>',lambda e:self.base_release(),add='+')
        root.bind_all('<ButtonRelease-1>',lambda e:self.base_release(),add='+')
        root.bind('<FocusOut>',lambda e:root.after(20,lambda:self.base_release() if root.focus_displayof() is None else None),add='+')
        self.base_preview_text=tk.StringVar();ttk.Label(base,textvariable=self.base_preview_text).pack(anchor='w')
        self.field(base,'Preview pulse (500–2500µs)',self.base_target)
        self.base_target.trace_add('write',lambda *_:self.base_target_changed())
        ttk.Checkbutton(base,text='Reverse drawing direction',variable=self.base_reverse,command=self.save_base_position).pack(anchor='w')
        self.field(base,'Move time (0.2–30s; speed capped at 600µs/s)',self.base_seconds)
        self.field(base,'Water bottle direction (0–180°)',self.water_angle)
        row=ttk.Frame(base);row.pack(fill='x',pady=4)
        ttk.Button(row,text='Engage at preview…',command=lambda:self.attempt(lambda:self.move_base(True))).pack(side='left',expand=True,fill='x')
        ttk.Button(row,text='Move to preview',command=lambda:self.attempt(self.move_base)).pack(side='left',expand=True,fill='x')
        row=ttk.Frame(base);row.pack(fill='x',pady=4)
        ttk.Button(row,text='Mark preview as FRONT',command=self.mark_base_front).pack(side='left',expand=True,fill='x')
        ttk.Button(row,text='Add base pose to routine',command=lambda:self.attempt(self.add_base_pose)).pack(side='left',expand=True,fill='x')
        self.base_status=tk.StringVar(value='Base released · physical position unknown')
        ttk.Label(base,textvariable=self.base_status,wraplength=460).pack(anchor='w',pady=4)
        ttk.Label(base,text='External power and common ground are already confirmed.\nFirst engagement can jump. Base poses run sequentially with arm checkpoints.\nOld continuous-base timed turns are blocked; replace them with base poses.',wraplength=460).pack(anchor='w')
        self.draw_base()
        cal_host=cal
        cal_scroll=tk.Canvas(cal_host,highlightthickness=0)
        cal_bar=ttk.Scrollbar(cal_host,orient='vertical',command=cal_scroll.yview)
        cal_scroll.configure(yscrollcommand=cal_bar.set)
        cal_bar.pack(side='right',fill='y');cal_scroll.pack(side='left',fill='both',expand=True)
        cal=ttk.Frame(cal_scroll);cal_window=cal_scroll.create_window(0,0,window=cal,anchor='nw')
        cal.bind('<Configure>',lambda e:cal_scroll.configure(scrollregion=cal_scroll.bbox('all')))
        cal_scroll.bind('<Configure>',lambda e:cal_scroll.itemconfigure(cal_window,width=e.width))
        self.power=tk.BooleanVar(value=True);ttk.Label(pose,text='External power and common ground already confirmed.').pack(anchor='w')
        ttk.Label(test,text='External power and common ground already confirmed.').pack(anchor='w',pady=4)
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
        actions=ttk.Frame(tabs,padding=10);actions_tab=actions;tabs.add(actions,text='Actions')
        actions_host=actions
        actions_scroll=tk.Canvas(actions_host,highlightthickness=0)
        actions_bar=ttk.Scrollbar(actions_host,orient='vertical',command=actions_scroll.yview)
        actions_scroll.configure(yscrollcommand=actions_bar.set)
        actions_bar.pack(side='right',fill='y');actions_scroll.pack(side='left',fill='both',expand=True)
        actions=ttk.Frame(actions_scroll);actions_window=actions_scroll.create_window(0,0,window=actions,anchor='nw')
        actions.bind('<Configure>',lambda e:actions_scroll.configure(scrollregion=actions_scroll.bbox('all')))
        actions_scroll.bind('<Configure>',lambda e:actions_scroll.itemconfigure(actions_window,width=e.width))
        ttk.Label(actions,text='Actions & emotions',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=8)
        self.disable_action_base=tk.BooleanVar(value=self.p.get('studio_ui',{}).get('disable_action_base',True))
        ttk.Checkbutton(actions,text='Disable base rotation · previews AND robot actions',variable=self.disable_action_base,command=self.change_action_base).pack(anchor='w',pady=6)
        ttk.Label(actions,text='Tick while calibrating the arm. Manual base controls stay available.',wraplength=470).pack(anchor='w')
        ttk.Label(actions,text='Expressive gestures · one click plays the whole preview.\nRest is your home pose; real checkpoints take priority.\nStarter guesses use small movements shaped by the lamp model.',wraplength=470).pack(anchor='w',pady=8)
        self.roles={};self.role_boxes=[]
        for key in ('Rest','Slump','Water','Stretch'):
            row=ttk.Frame(actions);row.pack(fill='x',pady=4);ttk.Label(row,text=key,width=10).pack(side='left')
            var=tk.StringVar(value=self.p.get('roles',{}).get(key,''));self.roles[key]=var
            box=ttk.Combobox(row,textvariable=var,state='readonly');box.pack(side='left',fill='x',expand=True);self.role_boxes.append(box)
        ttk.Button(actions,text='Save action checkpoint choices',command=lambda:self.attempt(self.save_roles)).pack(fill='x',pady=6)
        ttk.Button(actions,text='Use current picture as action Rest',command=lambda:self.attempt(self.set_action_home)).pack(fill='x',pady=4)
        ttk.Button(actions,text='Load editable starter checkpoints',command=lambda:self.attempt(self.load_action_starters)).pack(fill='x',pady=6)
        self.action_style=tk.StringVar(value='Robot chirps');ttk.Combobox(actions,textvariable=self.action_style,values=['Robot chirps','Musical tones'],state='readonly').pack(fill='x',pady=8)
        for key in ('Slump','Water','Stretch','Sad','Happy'):
            row=ttk.Frame(actions);row.pack(fill='x',pady=3)
            ttk.Button(row,text='▶ Play '+key+' preview',command=lambda k=key:self.attempt(lambda:self.preview(self.action_rows(k)))).pack(side='left',expand=True,fill='x')
            ttk.Button(row,text='Run '+key+' + sound',command=lambda k=key:self.attempt(lambda:self.run_action(k))).pack(side='left',expand=True,fill='x')
        self.emotion_light=tk.Label(actions,text='Emotion lighting preview',bg='#12232e',fg='white');self.emotion_light.pack(fill='x',pady=3)
        self.playback_text=tk.StringVar(value='One click plays the full animated gesture with sound.')
        ttk.Label(actions,textvariable=self.playback_text,wraplength=470).pack(anchor='w',pady=(10,4))
        self.playback_progress=tk.DoubleVar(value=0);ttk.Progressbar(actions,variable=self.playback_progress,maximum=100).pack(fill='x',pady=4)
        ttk.Button(profilebar,text='▶ Actions',command=lambda:tabs.select(actions_tab)).pack(side='left',padx=5)
        tabs.select(actions_tab)
        ttk.Label(routine,text='Select a checkpoint in Pose control, then add it here.\nEach row stores its own pulse values. Sound plays on arrival.',wraplength=490).pack(anchor='w')
        self.pause=tk.StringVar(value='1');self.sound=tk.StringVar(value='None');self.field(routine,'Pause after sound (seconds)',self.pause)
        ttk.Combobox(routine,textvariable=self.sound,values=SOUNDS,state='readonly').pack(fill='x',pady=6)
        ttk.Button(routine,text='Append selected checkpoint',command=self.append).pack(fill='x',pady=4)
        self.rows=tk.Listbox(routine,height=9,exportselection=False);self.rows.pack(fill='both',expand=True)
        row=ttk.Frame(routine);row.pack(fill='x')
        for label,fn in [('↑',lambda:self.reorder(-1)),('↓',lambda:self.reorder(1)),('Remove',self.remove_row)]:ttk.Button(row,text=label,command=fn).pack(side='left',expand=True,fill='x')
        ttk.Button(routine,text='Preview routine on screen',command=self.preview).pack(fill='x',pady=6)
        ttk.Button(routine,text='Run routine on robot',command=self.run).pack(fill='x',pady=6)
        self.apply_ui_preferences();self.refresh_profiles()
        root.protocol('WM_DELETE_WINDOW',self.close);self.refresh_lists();self.cal_list();self.draw();root.after(50,self.poll)
        root.bind_all('<ButtonRelease-1>',lambda e:self.end_control(),add='+')
        root.bind('<FocusOut>',lambda e:root.after(20,lambda:self.end_control() if root.focus_displayof() is None else None),add='+')
    def open_wireless_setup(self):
        if self.connected or self.busy:
            messagebox.showinfo('Disconnect first','Support the lamp, Release all, then use Disconnect before opening Wireless setup.',parent=self.root);return
        from wireless_setup import Setup
        self.auto_connect.set(False)
        window=tk.Toplevel(self.root);Setup(window)
        def close_setup():
            window.destroy();self.auto_connect.set(True);self.retry_at=time.monotonic()+1.5
        window.protocol('WM_DELETE_WINDOW',close_setup)
    def field(self,parent,label,var):
        row=ttk.Frame(parent);row.pack(fill='x',pady=4);ttk.Label(row,text=label).pack(side='left');ttk.Entry(row,textvariable=var,width=9).pack(side='right')
    def set_led_colour(self,colour):
        led_rgb(colour,100);self.led_colour.set(colour);self.led_sample.configure(bg=colour)
    def choose_led_colour(self):
        colour=colorchooser.askcolor(color=self.led_colour.get(),parent=self.root)[1]
        if colour:self.set_led_colour(colour)
    def apply_led(self,off=False):
        self.visual_enabled.set(False);self.toggle_visual_interaction()
        self.link.presence_light_context=None
        if self.busy:raise ValueError('Wait for the current action to finish or press STOP first.')
        if not off and not self.led_power.get():raise ValueError('Check the LED ring external 5V and common ground first.')
        self.send('led',None if off else led_rgb(self.led_colour.get(),round(self.led_brightness.get())))
    def attempt(self,fn):
        try:return fn()
        except Exception as e:messagebox.showerror('Lamp Studio',str(e),parent=self.root)
    def save(self):
        if self.previewing:self.cancel_preview()
        if hasattr(self,'action_style'):self.p['studio_ui']=self.capture_ui()
        self.p['base_position']=self.base_settings()
        ensure_full_pulse_range(self.p);check_project(self.p);tmp=FILE.with_suffix('.tmp');tmp.write_text(json.dumps(self.p,indent=2),encoding='utf-8');tmp.replace(FILE)
    def refresh_profiles(self):
        names=[]
        for path in PROFILES.glob('*.json'):
            if path.name.endswith('.previous.json'):continue
            try:names.append(json.loads(path.read_text(encoding='utf-8'))['profile_name'])
            except (ValueError,KeyError):pass
        self.profile_box.configure(values=sorted(names))
    def capture_ui(self):
        return dict(seconds=self.seconds.get(),speed=self.speed.get(),live_max=self.live_max.get(),base_speed=self.base_speed.get(),base_neutral=self.base_neutral.get(),base_seconds=self.base_seconds.get(),action_style=self.action_style.get(),disable_action_base=self.disable_action_base.get())
    def apply_ui_preferences(self):
        for key,value in self.p.get('studio_ui',{}).items():
            if key in ('seconds','speed','live_max','base_speed','base_neutral','base_seconds','action_style','disable_action_base'):getattr(self,key).set(value)
        self.live_enabled.set(False)
    def profile_path(self,name):
        if not name.strip() or any(ch in name for ch in '/\\:*?"<>|') or name.rstrip(' .')!=name:raise ValueError('Choose a simple profile name without path characters.')
        return PROFILES/(name+'.json')
    def save_profile(self):
        name=self.profile_name.get().strip();path=self.profile_path(name)
        if name.casefold()=='final draft' or (path.exists() and json.loads(path.read_text(encoding='utf-8')).get('profile_locked')):
            raise ValueError('This profile is locked. Enter a different name to save an editable copy; final draft will stay unchanged.')
        self.p['preview_pulse']=self.pulse();self.p['observed_angles']=copy.deepcopy(self.real_angles)
        self.p['base_position']=self.base_settings()
        self.p['config']=self.config();self.p['studio_ui']=self.capture_ui();self.p['base_reverse']=self.base_reverse.get();self.p['profile_name']=name
        self.p.pop('profile_locked',None);self.p.pop('locked_at',None)
        self.save();PROFILES.mkdir(exist_ok=True)
        if path.exists():path.with_suffix('.previous.json').write_text(path.read_text(encoding='utf-8'),encoding='utf-8')
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(self.p,indent=2),encoding='utf-8');tmp.replace(path)
        self.refresh_profiles();self.status.set('Profile saved: '+name+'. All adjustment tools remain available.')
    def load_profile(self):
        if self.connected or self.busy:raise ValueError('Use Disconnect first (support the lamp), then load the profile.')
        candidate=check_project(json.loads(self.profile_path(self.profile_name.get().strip()).read_text(encoding='utf-8')))
        locked=candidate.get('profile_locked',False)
        self.cancel_preview();self.cancel_match();self.cancel_range();self.p=candidate if locked else upgrade_directions(candidate)
        if locked:
            # Never migrate or write the archived calibration. Editing takes
            # place in an explicitly named working copy, not the locked file.
            self.p=copy.deepcopy(candidate);self.p.pop('profile_locked',None);self.p.pop('locked_at',None)
            self.p['profile_name']=candidate['profile_name']+' (working copy)'
            self.profile_name.set(self.p['profile_name'])
        else:ensure_full_pulse_range(self.p)
        base_settings=self.p.get('base_position',{});self.base_reverse.set(base_settings.get('reverse',False));self.base_front=base_settings.get('front',90);self.water_angle.set(str(base_settings.get('water_angle',self.base_front+90 if self.base_front<=90 else self.base_front-90)));self.base_target.set(base_settings.get('preview',1500));self.draw_base();self.real_angles=self.p.get('observed_angles')
        for var,value in zip(self.pulses,self.p.get('preview_pulse',self.p['config']['start'])):var.set(value)
        for var,value in zip(self.lengths,self.p['lengths']):var.set(str(value))
        for key,var in self.roles.items():var.set(self.p.get('roles',{}).get(key,''))
        self.apply_ui_preferences();self.save();self.refresh_lists();self.cal_list();self.draw();self.status.set('Locked profile loaded into an editable working copy; original stays unchanged. Live control is off.' if locked else 'Profile loaded; live control remains off.')
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
            if not self.previewing:c.create_text((a[0]+b[0])/2,(a[1]+b[1])/2-14,text=name,fill='#d8e5ec',font=('Segoe UI',8))
        for i,(x,y) in enumerate(pts[:3]):
            c.create_oval(x-5,y-5,x+5,y+5,fill='#12232e',outline=COLORS[i],width=3)
            if not self.previewing:c.create_text(x-9,y-10,text=('J1 lift','J2 elbow','J3 head tilt')[i],anchor='e',fill=COLORS[i],font=('Segoe UI',8,'bold'))
        # The final link describes the head orientation. Face may be flipped
        # independently of the servo map to match the physical shade mounting.
        x,y=pts[3];px,py=pts[2];length=max(.001,math.hypot(x-px,y-py));sign=self.p.get('head_face_sign',1)
        ux,uy=(x-px)/length*sign,(y-py)/length*sign;nx,ny=-uy,ux
        def point(along,side):return (x+along*ux+side*nx,y+along*uy+side*ny)
        front=point(13,0)
        rgb=getattr(self,'preview_rgb',[231,200,109]);light='#'+''.join(f'{v:02x}' for v in rgb)
        c.create_polygon(*point(15,-10),*point(50,-22),*point(50,22),*point(15,10),fill=light,stipple='gray75',outline='')
        c.create_polygon(*point(-13,-7),*point(12,-13),*point(12,13),*point(-13,7),fill='#e7b45d',outline='#ffe5a0',width=2)
        c.create_line(*point(13,-12),*point(13,12),fill=light,width=5)
        c.create_line(*front,*point(62,0),fill='#fff0a5',width=2,arrow='last')
        c.create_text(*point(72,0),text='FRONT',fill='#fff0a5',font=('Segoe UI',8,'bold'))
        if not self.previewing:c.create_text(x,y-25,text='LAMP HEAD',fill='#fff0a5',font=('Segoe UI',8,'bold'))
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
            if not self.previewing:self.draw_range(pts)
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
            self.live_enabled.set(False);self.status.set('Connect and engage the arm joints; live dragging then works automatically.');return
        self.status.set('Live dragging enabled. Drag top arm or pulse sliders; release to stop. Speed capped at600µs/s.')
    def start_control(self):
        self.live_enabled.set(bool(self.connected and self.state and self.state['active'][:3]==[1,1,1] and not self.range_edit.get() and self.match_angles is None and not self.previewing and (not self.busy or self.live_stream)))
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
        self.preview_token+=1;self.busy=True
        if kind=='slump' and isinstance(data,tuple):
            self.performance_active=True;self.performance_started=time.monotonic()
            self.end_control();self.base_release();self.open_preview_view(live=True)
            self.preview_phase.set('Preparing robot sequence…');self.preview_cue.set('Sound: waiting for cue')
            self.playback_progress.set(0);self.playback_text.set('Robot performance · preparing starting pose')
        self.link.submit(kind,data)
    def ready(self):
        if not self.connected or not self.power.get():raise ValueError('Connect the board first.')
        if self.busy:raise ValueError('Wait for completion or press STOP.')
    def test_apply(self,index):
        self.ready()
        pulse=int(self.test_pulses[index].get());finite(pulse,500,2500)
        if not messagebox.askokcancel('Apply one servo pulse',f'Apply {pulse}µs to joint {index+1} only? Initial engagement or a large change can jump. Support/unload the lamp and check free travel.',parent=self.root):return
        self.end_control();self.live_enabled.set(False)
        self.send('engage',(index,pulse,self.config()))
    def test_nudge(self,index,direction):
        self.ready()
        step=int(self.test_step.get());finite(step,1,2000)
        if not self.state or not self.state['active'][index]:raise ValueError('Apply a starting pulse to this servo first.')
        old=self.state['pulse'][index];pulse=max(500,min(2500,old+direction*step))
        if pulse==old:self.status.set('Software limit reached; no command sent.');return
        if step>50 and not messagebox.askokcancel('Large test step',f'Move joint {index+1} from {old} to {pulse}µs? This is a direct test step; use 10µs for endpoint checks.',parent=self.root):return
        self.end_control();self.live_enabled.set(False)
        self.test_pulses[index].set(str(pulse));self.send('engage',(index,pulse,self.config()))
    def base_settings(self):
        return dict(preview=round(self.base_target.get()),reverse=self.base_reverse.get(),front=self.base_front,water_angle=finite(float(self.water_angle.get()),0,180))
    def save_base_position(self):
        self.draw_base();self.save()
    def mark_base_front(self):
        self.base_front=base_angle(self.base_target.get(),self.base_reverse.get());self.save_base_position()
    def draw_base(self):
        if not hasattr(self,'base_canvas'):return
        try:pulse=finite(float(self.base_target.get()),500,2500)
        except (ValueError,tk.TclError):return
        c=self.base_canvas;c.delete('all');x=max(220,c.winfo_width())/2;y=115;r=75
        def point(angle,radius=r):
            theta=math.radians(angle-self.base_front-90)
            return x+radius*math.cos(theta),y+radius*math.sin(theta)
        angle=base_angle(pulse,self.base_reverse.get())
        for a in range(0,180,3):c.create_line(*point(a),*point(a+3),fill='#506979',width=2)
        c.create_oval(x-28,y-28,x+28,y+28,fill='#354f5d',outline='#8aa4ae')
        if self.state and self.state['active'][3] and 500<=self.state['pulse'][3]<=2500:
            c.create_line(x,y,*point(base_angle(self.state['pulse'][3],self.base_reverse.get())),fill='#f6b85a',width=3,dash=(5,3))
        c.create_line(x,y,*point(angle),fill='#36b8bd',width=6,arrow='last')
        c.create_text(x,12,text='FRONT ↑ · TOP VIEW',fill='white')
        for a in (0,90,180):c.create_text(*point(a,r+16),text=str(a)+'°',fill='#c8d5de')
        c.create_text(x,200,text='Teal: preview · Gold: last command · no measured feedback',fill='#c8d5de',font=('Segoe UI',8))
        if hasattr(self,'base_preview_text'):self.base_preview_text.set(f'Preview {angle:.1f}° · {round(pulse)}µs · 180° assumed travel')
    def base_point(self,event):
        if (self.busy and not self.base_control_held) or self.previewing:return
        if not self.base_control_held:self.start_base_drag()
        x=max(220,self.base_canvas.winfo_width())/2;y=115
        angle=(math.degrees(math.atan2(event.y-y,event.x-x))+90+self.base_front)%360
        if angle>180:angle=0 if angle>270 else 180
        if self.base_reverse.get():angle=180-angle
        self.base_target.set(round(500+angle*2000/180))
    def start_base_drag(self):
        if self.busy or self.previewing or self.range_edit.get() or self.match_angles is not None:return
        self.base_control_held=True
        self.base_drag_previous=(round(self.base_target.get()),time.monotonic())
    def base_target_changed(self):
        self.draw_base()
        if not self.base_control_held or self.previewing:return
        if self.range_edit.get() or self.match_angles is not None:return
        if self.busy and not self.base_stream:return
        if not self.connected or not self.state or not self.state['active'][3]:return
        now=time.monotonic()
        try:target=round(finite(float(self.base_target.get()),500,2500))
        except (ValueError,tk.TclError):return
        previous,when=self.base_drag_previous or (target,now-.05)
        speed=max(10,min(600,round(abs(target-previous)/max(.015,now-when))))
        self.base_drag_previous=(target,now)
        self.link.base_live_target=(target,speed,now)
        if not self.link.base_live_held:
            self.base_stream=True
            self.link.base_live_held=True
            self.attempt(lambda:self.send('slump',dict(base_live=True)))
    def base_pose_row(self):
        pulse=int(round(self.base_target.get()));finite(pulse,500,2500)
        return dict(type='base_position',name='Base position',pulse=pulse,seconds=finite(float(self.base_seconds.get()),.2,30))
    def move_base(self,engage=False):
        self.ready();row=self.base_pose_row()
        if engage and not messagebox.askokcancel('Engage SG90 base',f"Apply {row['pulse']}µs to GPIO15? First engagement can jump. Support the lamp and check clearance.",parent=self.root):return
        self.end_control();self.live_enabled.set(False)
        self.send('slump',dict(base_position=row,engage=engage))
    def add_base_pose(self):
        self.p['routine'].append(self.base_pose_row());self.save();self.refresh_lists()
        self.status.set('Base position checkpoint added. Preview in Routine; no movement sent.')
    def base_row(self,d,hold=False):
        raise ValueError('Continuous-base controls are disabled. Use SG90 position checkpoints.')
        if self.base_reverse.get():d=-d
        speed=finite(float(self.base_speed.get()),1,100);neutral=int(self.base_neutral.get());base_command(d,speed,neutral)
        return dict(type='base',name='Base '+('reverse' if d<0 else 'forward'),direction=d,speed=speed,neutral=neutral,seconds=10 if hold else finite(float(self.base_seconds.get()),.1,10),hold=hold)
    def base_hold(self,d):
        self.ready();row=self.base_row(d,True)
        if self.match_angles is not None:raise ValueError('Finish picture matching first.')
        self.link.base_held=True;self.send('slump',([row],self.config(),self.count))
    def base_release(self):
        self.link.base_held=False
        self.link.base_live_held=False;self.base_control_held=False
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
    def gesture_config(self,rows):
        cfg=self.config()
        if rows and all(row.get('gesture_speed')==600 for row in rows):cfg['max_speed']=600
        return cfg
    def set_action_home(self):
        if self.busy or self.previewing:raise ValueError('Stop the preview or movement first.')
        self.p['poses']['My action Rest']=self.pulse();self.roles['Rest'].set('My action Rest');self.save_roles();self.refresh_lists()
        self.status.set('Current picture saved as action Rest. No robot movement sent.')
    def change_action_base(self):
        if self.busy:
            self.disable_action_base.set(not self.disable_action_base.get())
            messagebox.showinfo('Stop first','Stop the running action before changing base rotation.',parent=self.root);return
        self.cancel_preview();self.preview_plan=None;self.save()
        self.status.set('Base rotation disabled in previews and action runs.' if self.disable_action_base.get() else 'Base rotation enabled. Preview again before running.')
    def filter_action_base(self,rows):
        return without_base_motion(rows) if self.disable_action_base.get() else copy.deepcopy(rows)
    def action_rows(self,kind):
        return self.filter_action_base(self._action_rows(kind))
    def _action_rows(self,kind):
        if kind=='Happy':
            project=copy.deepcopy(self.p);project['base_position']=self.base_settings()
            return build_happy(project,{key:var.get() for key,var in self.roles.items()},self.action_style.get()=='Musical tones')
        if kind=='Sad':
            base_start=self.state['pulse'][3] if self.connected and self.state and self.state['active'][3] else round(self.base_target.get())
            return build_sad(self.p,{key:var.get() for key,var in self.roles.items()},self.action_style.get()=='Musical tones',base_start)
        rest=self.roles['Rest'].get();target=self.roles[kind].get()
        if rest not in self.p['poses'] or target not in self.p['poses']:raise ValueError('Select Rest and '+kind+' checkpoints, or load the editable starters.')
        project=copy.deepcopy(self.p);project['base_position']=self.base_settings()
        return build_gesture(project,{key:var.get() for key,var in self.roles.items()},kind,self.action_style.get()=='Musical tones')
    def run_action(self,kind):
        self.ready();rows=self.action_rows(kind)
        if messagebox.askokcancel('Run '+kind,'Run '+kind+' using the selected checkpoints? Released joints will engage at the starting pose. Check clearance.',parent=self.root):
            self.save_roles();self.send('slump',(rows,self.run_config(rows,self.gesture_config(rows)),self.count))
    def run_config(self,rows,cfg,start=None,base=None):
        cfg=copy.deepcopy(cfg);cfg['run_engage']=True
        cfg['run_start']=list(start or next((r['pulse'] for r in rows if r.get('type')!='base_position'),cfg['start']))
        cfg['run_base_start']=int(base if base is not None else self.state['pulse'][3] if self.state and self.state['active'][3] else round(self.base_target.get()))
        return cfg
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
            text+=(f" · {r['pulse']}µs" if r.get('type')=='base_position' else ' · OLD continuous turn — replace' if r.get('type')=='base' else f" + {r['pause']}s · {SOUNDS[r['sound']+1]}")
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
        rows=self.filter_action_base(self.p['routine'])
        if not rows:raise ValueError('No arm checkpoints to run. Base-only steps are skipped when base rotation is disabled.')
        if messagebox.askokcancel('Run checkpoints','Run the saved checkpoints on the lamp? Released joints will engage at the starting pose. STOP cancels the remaining routine.',parent=self.root):self.send('slump',(rows,self.run_config(rows,self.config()),self.count))
    def cancel_preview(self):
        if self.previewing:
            self.preview_token+=1;self.previewing=False;self.preview_plan=None
            winsound.PlaySound(None,0)
            if hasattr(self,'preview_phase'):self.preview_phase.set('Preview stopped')
    def preview(self,rows=None):self.attempt(lambda:self._preview(rows))
    def _preview(self,rows=None):
        if self.busy or self.match_angles is not None or self.range_edit.get():raise ValueError('Finish movement or calibration before previewing.')
        self.cancel_preview();self.end_control();self.live_enabled.set(False)
        rows=self.filter_action_base(self.p['routine'] if rows is None else rows)
        if not rows:raise ValueError('Add routine checkpoints first.')
        if any(row.get('type')=='base' for row in rows):raise ValueError('Replace old timed base turns with SG90 position checkpoints before previewing.')
        candidate=copy.deepcopy(self.p);candidate['routine']=rows;check_project(candidate)
        cfg=self.gesture_config(rows);start=self.state['pulse'][:3].copy() if self.connected and self.state and self.state['active'][:3]==[1,1,1] else self.pulse()
        check_pose(start,cfg)
        self.preview_plan=dict(rows=rows,cfg=cfg,start=start,calibration=copy.deepcopy(self.p['calibration']),lengths=self.p['lengths'].copy(),head_face_sign=self.p.get('head_face_sign',1))
        base_start=self.state['pulse'][3] if self.connected and self.state and self.state['active'][3] else round(self.base_target.get())
        self.preview_plan['base_start']=base_start
        self.preview_plan['base_geometry']=(self.base_reverse.get(),self.base_front)
        light_origin=getattr(self,'last_led_rgb',led_rgb(self.led_colour.get(),round(self.led_brightness.get()))).copy()
        preview_light=[light_origin.copy()]
        self.preview_rgb=light_origin.copy();self.open_preview_view()
        self.preview_phase.set('Preparing preview');self.preview_cue.set('Sound cue: none yet')
        self.base_target.set(base_start)
        if self.real_angles is None:self.real_reference=start.copy()
        self.previewing=True;self.preview_token+=1;token=self.preview_token
        estimate=0.;audio_end=0.;previous=start;previous_base=base_start
        for row in rows:
            if row.get('type')=='base_position':estimate+=base_motion_duration(previous_base,row);previous_base=row['pulse'];continue
            row=coordinated_row(previous,row,cfg['max_speed'],previous_base)
            eased=row.get('easing')=='quintic'
            if eased and row['sound']>=0:estimate=max(estimate,audio_end);audio_end=estimate+SOUND_SECONDS[row['sound']]
            estimate+=trajectory_duration(previous,row,cfg['max_speed']) if eased else preview_motion(previous,row['pulse'],row['seconds'],cfg['max_speed'],0)[1]
            if not eased and row['sound']>=0:estimate+=SOUND_SECONDS[row['sound']]
            estimate+=row['pause'];previous=row['pulse']
            previous_base=row.get('base_pulse',previous_base)
        estimate=max(estimate,audio_end);playback_begin=time.monotonic()
        def progress():
            if token!=self.preview_token:return
            elapsed=time.monotonic()-playback_begin
            self.playback_progress.set(min(100,100*elapsed/max(.1,estimate)))
            self.playback_text.set(f'Preview · {elapsed:.1f}s / approximately {estimate:.1f}s · no robot movement')
            self.draw_preview_view()
            if self.previewing:self.root.after(50,progress)
        progress()
        sound_until=[0.0]
        def play_cue(index):
            self.preview_cue.set('Sound cue: '+SOUNDS[index+1]+' · laptop speaker')
            winsound.PlaySound(str(HERE/'sounds'/(SOUND_FILES[index]+'.wav')),winsound.SND_FILENAME|winsound.SND_ASYNC)
            sound_until[0]=time.monotonic()+SOUND_SECONDS[index]
        for var,value in zip(self.pulses,start):var.set(value)
        def next_row(index):
            if token!=self.preview_token:return
            if index>=len(rows):
                remaining=sound_until[0]-time.monotonic()
                if remaining>0:self.root.after(max(1,round(remaining*1000)),lambda:next_row(index));return
                self.previewing=False;self.preview_phase.set('Preview complete');self.playback_progress.set(100);self.playback_text.set('Preview complete · Run previewed plan uses the same gesture.');self.status.set('Preview complete. Run previewed plan uses this same motion, pauses and sounds.');self.draw_preview_view();return
            row=rows[index];initial=self.pulse();begin=time.monotonic();self.status.set('SCREEN ONLY · '+row['name'])
            self.preview_phase.set(row['name'])
            if row.get('type')=='base_position':
                start_base=self.base_target.get();duration=base_motion_duration(start_base,row)
                def base_tick():
                    if token!=self.preview_token:return
                    t=min(1,(time.monotonic()-begin)/duration) if duration else 1
                    self.base_target.set(start_base+(row['pulse']-start_base)*t)
                    if t<1:self.root.after(30,base_tick)
                    else:next_row(index+1)
                base_tick();return
            if row.get('type')=='base':
                self.base_status.set('Preview: '+row['name']+f" for {row['seconds']}s · heading unknown")
                self.root.after(round(row['seconds']*1000),lambda:next_row(index+1));return
            eased=row.get('easing')=='quintic'
            start_base=self.base_target.get()
            row=coordinated_row(initial,row,cfg['max_speed'],start_base)
            light_start=preview_light[0].copy()
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
                if 'light_progress' in row or 'warm_level' in row or 'light_rgb' in row:
                    t=min(1,(time.monotonic()-begin)/max(.001,duration))
                    rgb=sample_emotion_light(light_origin,row,light_start,t)
                    preview_light[0]=rgb;self.show_emotion_light(rgb)
                if 'base_pulse' in row:
                    t=min(1,(time.monotonic()-begin)/max(.001,duration))
                    self.base_target.set(start_base+(row['base_pulse']-start_base)*t)
                self.draw()
                if time.monotonic()-begin<duration:self.root.after(30,tick)
                else:arrived()
            tick()
        next_row(0)
    def run_previewed(self):
        self.ready()
        if self.previewing:raise ValueError('Wait for the preview to finish first.')
        plan=self.preview_plan
        if plan and any(row.get('type')=='base_position' or 'base_pulse' in row for row in plan['rows']):
            if self.state and self.state['active'][3] and self.state['pulse'][3]!=plan['base_start']:raise ValueError('Base start changed. Preview again.')
            if (self.base_reverse.get(),self.base_front)!=plan['base_geometry']:raise ValueError('Base drawing calibration changed. Preview again.')
        if not plan:raise ValueError('Preview a complete action or routine first.')
        if plan['calibration']!=self.p['calibration'] or plan['lengths']!=self.p['lengths'] or plan.get('head_face_sign',1)!=self.p.get('head_face_sign',1):raise ValueError('The lamp model changed. Preview again before running.')
        if any(row.get('type')!='base_position' for row in plan['rows']) and self.state and any(active and pulse!=target for active,pulse,target in zip(self.state['active'][:3],self.state['pulse'][:3],plan['start'])):raise ValueError('The robot starting pose differs from the preview. Preview again from its current position.')
        if messagebox.askokcancel('Run previewed plan','Run exactly the previewed checkpoints, speed limit, pauses and sounds? Released joints will engage at the preview starting pose. Check clearance.',parent=self.root):
            self.send('slump',(copy.deepcopy(plan['rows']),self.run_config(plan['rows'],plan['cfg'],plan['start'],plan['base_start']),self.count))
    def show_emotion_light(self,rgb):
        self.preview_rgb=rgb.copy()
        colour='#'+''.join(f'{x:02x}' for x in rgb)
        self.emotion_light.configure(bg=colour,text=f'Emotion light · RGB {rgb[0]}, {rgb[1]}, {rgb[2]}',fg='white' if max(rgb)<150 else 'black')
        self.led_sample.configure(bg=colour)
        self.draw_preview_view()
    def open_preview_view(self,live=False):
        if hasattr(self,'preview_window') and self.preview_window.winfo_exists():
            self.set_monitor_mode(live);self.preview_window.deiconify();self.preview_window.lift();return
        w=tk.Toplevel(self.root);self.preview_window=w;w.title('Lamp Studio · action preview');w.geometry('1080x760');w.minsize(860,650);w.configure(bg='#12232e')
        self.monitor_heading=tk.StringVar()
        tk.Label(w,textvariable=self.monitor_heading,bg='#12232e',fg='#dceaf2',font=('Segoe UI',18,'bold')).pack(anchor='w',padx=18,pady=(12,4))
        self.preview_phase=tk.StringVar(value='Preparing preview');self.preview_cue=tk.StringVar(value='Sound cue: none yet')
        tk.Label(w,textvariable=self.preview_phase,bg='#12232e',fg='white',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=18)
        body=tk.Frame(w,bg='#12232e');body.pack(fill='both',expand=True,padx=12,pady=8)
        arm=tk.Frame(body,bg='#182d39');arm.pack(side='left',fill='both',expand=True,padx=(0,8))
        tk.Label(arm,text='ARM · SIDE VIEW',bg='#182d39',fg='#a8c9d9',font=('Segoe UI',11,'bold')).pack(pady=6)
        self.preview_arm=tk.Canvas(arm,bg='#182d39',highlightthickness=0);self.preview_arm.pack(fill='both',expand=True)
        right=tk.Frame(body,bg='#12232e',width=330);right.pack(side='right',fill='y');right.pack_propagate(False)
        self.preview_base=tk.Canvas(right,bg='#182d39',height=290,highlightthickness=0);self.preview_base.pack(fill='x')
        self.preview_lights=tk.Canvas(right,bg='#182d39',height=210,highlightthickness=0);self.preview_lights.pack(fill='both',expand=True,pady=(8,0))
        tk.Label(w,textvariable=self.preview_cue,bg='#12232e',fg='#a8c9d9').pack(anchor='w',padx=18)
        ttk.Progressbar(w,variable=self.playback_progress,maximum=100).pack(fill='x',padx=18,pady=6)
        ttk.Label(w,textvariable=self.playback_text).pack(fill='x',padx=18)
        buttons=ttk.Frame(w,padding=8);buttons.pack(fill='x')
        ttk.Checkbutton(buttons,text='Disable base rotation',variable=self.disable_action_base,command=self.change_action_base).pack(side='left',padx=8)
        self.monitor_stop=ttk.Button(buttons,text='Stop preview',command=self.cancel_preview);self.monitor_stop.pack(side='left')
        self.monitor_run=ttk.Button(buttons,text='Run previewed plan on robot…',command=lambda:self.attempt(self.run_previewed));self.monitor_run.pack(side='right')
        tk.Label(w,text='Estimated geometry and commanded angles · no collision or position sensors',bg='#12232e',fg='#92aebb').pack(pady=(0,8))
        def close():
            if self.performance_active:w.withdraw()
            else:self.cancel_preview();w.destroy()
        w.protocol('WM_DELETE_WINDOW',close)
        for canvas in (self.preview_arm,self.preview_base,self.preview_lights):canvas.bind('<Configure>',lambda e:self.draw_preview_view())
        self.set_monitor_mode(live)
    def set_monitor_mode(self,live):
        self.monitor_heading.set('ROBOT PERFORMANCE · live commands' if live else 'ACTION PREVIEW · screen only')
        self.preview_window.title('Lamp Studio · robot performance' if live else 'Lamp Studio · action preview')
        self.monitor_stop.configure(text='STOP robot + sound' if live else 'Stop preview',command=self.stop if live else self.cancel_preview)
        self.monitor_run.configure(state='disabled' if live else 'normal')
    def draw_preview_view(self):
        if not hasattr(self,'preview_window') or not self.preview_window.winfo_exists():return
        rgb=getattr(self,'preview_rgb',[0,0,0]);colour='#'+''.join(f'{v:02x}' for v in rgb)
        c=self.preview_arm;c.delete('all');pts=self.coords(self.pulse(),c)
        if self.performance_active and isinstance(self.performance_target,list):
            target=self.coords(self.performance_target,c);c.create_line(*[value for pt in target for value in pt],fill='#879dad',width=4,dash=(6,5))
        for i in range(3):c.create_line(*pts[i],*pts[i+1],fill=COLORS[i],width=12,capstyle='round')
        self.lamp_details(c,pts)
        b=self.preview_base;b.delete('all');x=max(200,b.winfo_width())/2;y=140;r=90
        angle=base_angle(self.base_target.get(),self.base_reverse.get());relative=angle-self.base_front
        def point(a,radius=r):
            theta=math.radians(a-self.base_front-90);return x+radius*math.cos(theta),y+radius*math.sin(theta)
        b.create_text(x,18,text='BASE · TOP VIEW',fill='#a8c9d9',font=('Segoe UI',11,'bold'))
        b.create_text(x,40,text='FRONT ↑',fill='white')
        for a in range(0,180,3):b.create_line(*point(a),*point(a+3),fill='#526b7b',width=3)
        for a in (0,45,90,135,180):b.create_text(*point(a,r+16),text=f'{a}°',fill='#c6d8e3')
        b.create_oval(x-27,y-27,x+27,y+27,fill='#354f5d',outline='#8aa4ae')
        if self.performance_active and self.performance_base_target is not None:b.create_line(x,y,*point(base_angle(self.performance_base_target,self.base_reverse.get())),fill='#879dad',width=3,dash=(6,5),arrow='last')
        b.create_line(x,y,*point(angle),fill='#36d7d9',width=9,arrow='last')
        b.create_text(x,253,text=f'{angle:.0f}°  ·  {relative:+.0f}° from FRONT',fill='white',font=('Segoe UI',13,'bold'))
        l=self.preview_lights;l.delete('all');w=max(200,l.winfo_width());peak=max(rgb);level=peak/255
        hue=[round(v*255/peak) for v in rgb] if peak else [0,0,0];hue_colour='#'+''.join(f'{v:02x}' for v in hue)
        l.create_text(w/2,20,text='LIGHT · COLOUR & BRIGHTNESS',fill='#a8c9d9',font=('Segoe UI',10,'bold'))
        l.create_rectangle(18,40,w/2-5,105,fill=hue_colour,outline='#6c8b9d');l.create_rectangle(w/2+5,40,w-18,105,fill=colour,outline='#6c8b9d')
        l.create_text(w/4,122,text='Colour hue',fill='white');l.create_text(w*.75,122,text='Actual output',fill='white')
        l.create_rectangle(20,145,w-20,163,fill='#304653',outline='')
        l.create_rectangle(20,145,20+(w-40)*level,163,fill=hue_colour,outline='')
        l.create_text(w/2,183,text=f'Brightness {level:.0%} · RGB {rgb[0]}, {rgb[1]}, {rgb[2]}',fill='white',font=('Segoe UI',10,'bold'))
    def toggle_visual_interaction(self):
        self.visual_generation+=1
        self.link.presence_light_context=(self.visual_enabled.get(),False,0)
        # Keep episode latch across toggles; enabling is not a new sitting session.
        self.visual_status.set('等待新鲜久坐／低头状态' if self.visual_enabled.get() else '视觉联动已关闭')
    def poll_visual_interaction(self):
        if not self.visual_enabled.get() or self.visual_fetching or time.monotonic()<self.visual_next:return
        self.visual_fetching=True;self.visual_next=time.monotonic()+.5
        generation=self.visual_generation
        def fetch():
            try:
                with urllib.request.urlopen('http://127.0.0.1:8768/api/presence',timeout=1) as response:
                    result=json.load(response)
                self.events.put(('visual_presence',(generation,result,None)))
            except Exception as exc:self.events.put(('visual_presence',(generation,{},str(exc))))
        threading.Thread(target=fetch,daemon=True).start()
    def handle_visual_presence(self,data):
        self.visual_fetching=False
        generation,snapshot,error=data
        if generation!=self.visual_generation or not self.visual_enabled.get():return
        if error:
            self.link.presence_light_context=(True,False,0)
            self.visual_status.set('视觉服务不可用；未触发动作');return
        p=snapshot.get('presence') or {}
        remaining=max(0,3-(time.time()-p.get('updated',0)))
        self.link.presence_light_context=(True,visible_person(snapshot),time.monotonic()+remaining)
        ready=(self.connected and not self.busy and not self.previewing
               and not self.control_held and not self.base_control_held
               and self.match_angles is None and not self.range_edit.get()
               and self.state and all(self.state['active'][:4]))
        action=self.visual_trigger.update(snapshot,ready)
        if action:
            try:
                rows=self.action_rows(action)
                self.send('slump',(rows,self.gesture_config(rows),self.count))
                self.visual_status.set(('低头 5 秒：执行伸展' if action=='Stretch' else '久坐 10 秒：执行喝水')+'，本轮不再重复')
            except Exception as exc:self.visual_status.set('动作未执行：'+str(exc))
        else:
            self.visual_status.set('等待久坐 10 秒／低头 5 秒（每轮一次）' if snapshot.get('active') else '视觉采集已停止')
    def stop(self):
        if self.performance_active:
            self.performance_active=False;self.preview_phase.set('Robot sequence stopped');self.playback_text.set('Stopped · remaining steps cancelled')
        self.visual_enabled.set(False);self.toggle_visual_interaction()
        self.cancel_preview()
        self.end_control();self.live_enabled.set(False)
        self.base_release()
        self.preview_token+=1
        if self.connected:self.busy=True;self.link.submit('stop')
        self.status.set('Stopped. Remaining routine cancelled.')
    def release(self):
        self.visual_enabled.set(False);self.toggle_visual_interaction()
        self.cancel_preview()
        self.end_control();self.live_enabled.set(False)
        self.preview_token+=1
        if self.connected and messagebox.askokcancel('Support lamp','Release signals? Support the lamp so it cannot fall.',parent=self.root):self.busy=True;self.link.submit('off')
    def close(self):
        self.cancel_preview()
        self.end_control()
        if self.connected:
            if not messagebox.askokcancel('Close controller','Closing releases signals. Support the lamp first.',parent=self.root):return
            self.visual_enabled.set(False);self.toggle_visual_interaction()
            self.closing=True;self.auto_connect.set(False)
            self.preview_token+=1;self.link.submit('close')
        else:self.root.destroy()
    def disconnect_board(self):
        if self.busy:messagebox.showinfo('Wait','Stop the current operation first.',parent=self.root);return
        if self.connected:
            if not messagebox.askokcancel('Disconnect','Support the lamp. Disconnecting releases its outputs.',parent=self.root):return
            self.visual_enabled.set(False);self.toggle_visual_interaction()
            self.cancel_preview();self.end_control();self.live_enabled.set(False);self.auto_connect.set(False);self.disconnecting=True;self.busy=True;self.link.submit('close')
        else:self.auto_connect.set(False);self.status.set('Automatic reconnection paused. You can load profiles or preview offline.')
    def retry_connection(self):
        now=time.monotonic()
        if self.closing or self.disconnecting or self.connected or self.busy or not self.auto_connect.get() or now<self.retry_at:return
        self.retry_at=now+min(10,1.5*2**min(self.retry_count,3))
        if self.previewing or self.range_edit.get() or self.match_angles is not None:return
        self.connection.set('Searching USB + Wi-Fi…');self.send('connect')
    def poll(self):
        self.link.ui_alive=time.monotonic()
        if self.base_control_held and self.link.base_live_held and hasattr(self.link,'base_live_target'):
            target,speed,_=self.link.base_live_target;self.link.base_live_target=(target,speed,time.monotonic())
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='visual_presence':self.handle_visual_presence(data)
                elif kind=='connected':
                    self.connected=True;self.busy=False;self.count=data[1];self.retry_count=0;self.connection.set(f'{data[0]} · {self.count} sounds ready')
                    self.power.set(True)
                    self.live_enabled.set(False);self.status.set('Connected. Boot-held Rest is claimed without movement. Choose an action and press Run; released joints are prepared when you run. Interrupted actions are not resumed.')
                elif kind=='state':
                    self.state=data
                    if self.performance_active:
                        for i,value in enumerate(data['pulse'][:3]):
                            if data['active'][i] and 500<=value<=2500:self.pulses[i].set(value)
                        if data['active'][3] and 500<=data['pulse'][3]<=2500:self.base_target.set(data['pulse'][3])
                        self.draw_preview_view()
                    self.draw()
                    for i,label in enumerate(self.test_states):
                        label.set(f"Command: {data['pulse'][i]}µs · "+('engaged' if data['active'][i] else 'released; position unknown'))
                    self.base_status.set(f"Base command: {data['pulse'][3]}µs · "+('engaged (estimated position)' if data['active'][3] else 'released; position unknown'));self.draw_base()
                elif kind=='phase':self.status.set(data)
                elif kind=='finished':
                    if self.performance_active:
                        self.performance_active=False;self.preview_phase.set(str(data));self.playback_text.set('Sequence ended · '+str(data))
                    led_match=re.search(r'LED_STATUS[^\r\n]* r=(\d+) g=(\d+) b=(\d+)',str(data))
                    if led_match:self.last_led_rgb=list(map(int,led_match.groups()))
                    if self.base_stream:
                        self.base_release();self.base_stream=False
                        if self.state and self.state['active'][3]:self.base_target.set(self.state['pulse'][3])
                    was_live=self.live_stream;self.busy=False;self.live_stream=False;self.status.set(data)
                    if was_live:self.end_control();self.use_current()
                elif kind=='error':
                    if self.performance_active:
                        self.performance_active=False;self.preview_phase.set('Connection lost · sequence cancelled');self.playback_text.set(str(data))
                    self.visual_enabled.set(False);self.toggle_visual_interaction()
                    self.connected=False;self.busy=False;self.live_stream=False;self.live_enabled.set(False);self.end_control();self.base_release();self.power.set(False);self.state=None;self.preview_plan=None
                    self.retry_count+=1;self.retry_at=time.monotonic()+min(10,1.5*2**min(self.retry_count-1,3));self.connection.set('Disconnected · retry scheduled' if self.auto_connect.get() else 'Disconnected');self.status.set(data)
                    for label in self.test_states:label.set('Disconnected · physical position unknown')
                elif kind=='emotion_light':
                    self.last_led_rgb=data.copy();self.show_emotion_light(data)
                elif kind=='run_phase':
                    if self.performance_active:
                        self.preview_phase.set(f"{data['index']}/{data['total']} · {data['name']}")
                        self.performance_target=data['pulse'];self.performance_base_target=data['base'];self.draw_preview_view()
                elif kind=='run_progress':
                    if self.performance_active:
                        self.playback_progress.set(data)
                        self.playback_text.set(f'Robot performance · {data:.0f}% · {time.monotonic()-self.performance_started:.1f}s elapsed')
                elif kind=='run_sound':
                    if self.performance_active:self.preview_cue.set('Robot speaker · '+SOUNDS[data[0]+1]+' · '+data[1])
                elif kind=='run_complete':
                    if self.performance_active:
                        self.playback_progress.set(100);self.preview_phase.set('Robot sequence complete');self.playback_text.set('Complete · last commanded pose held')
                        self.performance_active=False;self.draw_preview_view()
                elif kind=='closed':
                    if self.disconnecting:
                        self.disconnecting=False;self.connected=False;self.busy=False;self.state=None;self.power.set(False);self.connection.set('Offline · auto reconnect paused')
                        self.link=VisualLink(lambda *e:self.events.put(e));continue
                    self.root.destroy();return
        except queue.Empty:pass
        self.poll_visual_interaction();self.retry_connection();self.root.after(50,self.poll)

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
