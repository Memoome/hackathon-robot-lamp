"""Explicit, externally powered greeting demo; no microphone or automatic motion."""
import datetime,json,pathlib,queue,re,threading,time,tkinter as tk
from tkinter import ttk,messagebox
import serial
from arm_controller import board_port,HERE
from live_control import STATUS,parse_status

START=(1000,600,2500);END=(1300,1900,500);STEP=300;INTERVAL=.5;SETTLE=.5
GLIDE_SPEED=600  # 300us per 0.5s, generated on-board in steps capped at10us.
AUDIO=rb'STATUS mode=OFFLINE_PCM revision=3 state=(\w+) busy=([01]) chip_ready=([01]) retained_bytes=\d+ volume=\d+ autoplay=OFF hello_state=(-?\d+)'

def frames(start,end,step=STEP):
    if len(start)!=3 or len(end)!=3 or step<=0 or any(not 500<=p<=2500 for p in (*start,*end)):raise ValueError('Invalid pose or step')
    current=tuple(start);result=[]
    while current!=tuple(end):
        current=tuple(min(b,a+step) if b>a else max(b,a-step) if b<a else a for a,b in zip(current,end));result.append(current)
    return result

class Cancelled(Exception):pass

class DemoLink:
    def __init__(self,emit):
        self.emit=emit;self.jobs=queue.Queue();self.cancel=threading.Event();self.ui_alive=time.monotonic();self.s=None;self.session=None;self.state=None;self.closing=False
        threading.Thread(target=self.worker,daemon=True).start()
    def submit(self,kind,data=None):
        if kind in ('prepare','run','sound'):self.cancel.clear()
        if kind in ('stop','off','close'):
            self.cancel.set()
            while True:
                try:self.jobs.get_nowait()
                except queue.Empty:break
        self.jobs.put((kind,data))
    def check(self):
        if self.cancel.is_set():raise Cancelled('Stopped by user. Hello was not started after cancellation.')
        if time.monotonic()-self.ui_alive>.8:raise Cancelled('Window stopped responding. Sequence cancelled.')
    def exchange(self,command,pattern=STATUS,timeout=1.5):
        if not self.s:raise RuntimeError('Connect first.')
        self.s.reset_input_buffer();self.s.write((command+'\r\n').encode());self.s.flush();raw=bytearray();until=time.monotonic()+timeout
        try:
            while time.monotonic()<until:
                raw.extend(self.s.read(4096))
                error=re.search(rb'(LIVE_ERROR[^\r\n]*|ERROR busy/not-ready[^\r\n]*|ERROR queue full)',raw)
                if error:raise RuntimeError(error[0].decode(errors='replace'))
                if re.search(pattern,raw):
                    if pattern==STATUS:
                        state=parse_status(raw)
                        if self.session is not None and state['session']!=self.session:raise RuntimeError('Board restarted. Reconnect; no automatic resume.')
                        self.state=state;self.emit('state',state)
                    return bytes(raw)
            raise RuntimeError('Reply timed out. Check USB, power and earlier controller windows.')
        finally:
            with (HERE/'greeting-demo.log').open('a',encoding='utf-8') as f:f.write(datetime.datetime.now().isoformat()+' '+command+'\n'+raw.decode(errors='replace')+'\n')
    def audio_state(self):
        raw=self.exchange('audio_test status',AUDIO);m=re.search(AUDIO,raw)
        return m[1].decode(),int(m[2]),int(m[3]),int(m[4])
    def pose(self,values,scene=None):
        self.check()
        command='arm_live pose '+' '.join(map(str,values))
        if scene:
            percent,direction,neutral=scene
            offset=round((2500-neutral if direction>0 else neutral-500)*percent/100)
            pulse=neutral+direction*offset
            command='arm_live scene '+' '.join(map(str,(*values,pulse,1000,neutral)))
        self.exchange(command)
        if self.state['pulse'][:3]!=list(values):raise RuntimeError('Board acknowledged an unexpected pose.')
    def wait_until(self,deadline):
        while time.monotonic()<deadline:
            self.check();time.sleep(min(.025,max(0,deadline-time.monotonic())))
    def smooth(self,goals,scene=None):
        self.check()
        initial=self.state['pulse'][:3]
        if any(not 500<=p<=2500 for p in initial):raise RuntimeError('Engage the starting pose first.')
        deadline=time.monotonic()+max(abs(a-b) for a,b in zip(initial,goals))/GLIDE_SPEED+4
        if scene:
            # The mini CLI accepts eight arguments. Start the board-timed base
            # with the existing pose, then start all three ramps in one short command.
            self.pose(initial,scene=scene)
        while True:
            self.check()
            command='arm_live glide '+' '.join(map(str,(*goals,GLIDE_SPEED)))
            self.exchange(command)
            self.emit('phase','Moving smoothly · '+str(tuple(self.state['pulse'][:3])))
            if self.state['pulse'][:3]==list(goals) and self.state['moving'][:3]==[0,0,0]:return
            if time.monotonic()>deadline:raise RuntimeError('Smooth motion timed out; stopped without playing Hello.')
            self.wait_until(time.monotonic()+.1)
    def hello(self):
        self.check();name,busy,ready,_=self.audio_state()
        if name!='READY' or busy or not ready:raise RuntimeError('Robot audio is not ready. No sound was started.')
        self.emit('phase','Setting robot speaker to100%...')
        self.exchange('audio_test volume 100',rb'VOLUME requested=100 actual=100 hardware_max=31 rc=0')
        until=time.monotonic()+3
        while True:
            self.check();name,busy,ready,_=self.audio_state()
            if name=='READY' and not busy and ready:break
            if time.monotonic()>until:raise RuntimeError('Volume change did not finish; Hello not started.')
            self.wait_until(time.monotonic()+.1)
        self.emit('phase','Speaking Hello through the robot speaker at100%...')
        self.exchange('audio_test hello',rb'HELLO_QUEUED')
        until=time.monotonic()+8
        while time.monotonic()<until:
            self.check();name,busy,ready,result=self.audio_state()
            if result==-1:raise RuntimeError('Board reported Hello playback failure or cancellation.')
            if result==2 and not busy:return
            self.wait_until(time.monotonic()+.12)
        raise RuntimeError('Hello playback did not complete in time.')
    def stop_hardware(self,release=False):
        if not self.s:return
        self.exchange('arm_live off' if release else 'arm_live freeze')
        self.s.write(b'audio_test stop\r\n');self.s.flush()
    def worker(self):
        while True:
            kind=None
            try:
                try:kind,data=self.jobs.get(timeout=.4)
                except queue.Empty:
                    if self.s and time.monotonic()-self.ui_alive<.8:self.exchange('arm_live ping')
                    continue
                if kind=='connect':
                    if self.s:self.s.close()
                    self.session=None;p=board_port();self.s=serial.Serial(port=None,baudrate=115200,timeout=.025,rtscts=False,dsrdtr=False)
                    self.s.dtr=False;self.s.rts=False;self.s.port=p;self.s.open()
                    self.exchange('arm_live status');self.session=self.state['session']
                    if any(self.state['active']):raise RuntimeError('Outputs active. Support the arm and close/release the older controller first.')
                    audio=self.audio_state();self.emit('connected',(p,audio))
                elif kind in ('stop','off','close'):
                    self.stop_hardware(kind!='stop');self.emit('finished','Stopped; position targets held.' if kind=='stop' else 'Signals released. Support the arm.')
                    if kind=='close':
                        if self.s:self.s.close()
                        self.emit('closed',None);return
                else:
                    if kind=='prepare':
                        self.exchange('arm_live status');old=self.state['pulse'][:3]
                        if all(old):self.smooth(START)
                        else:self.pose(START)
                        self.wait_until(time.monotonic()+SETTLE)
                        self.emit('finished','Starting pose set. Align/check the base manually, then Run greeting.')
                    elif kind=='run':
                        self.exchange('arm_live status')
                        if self.state['pulse'][:3]!=list(START) or self.state['active'][:3]!=[1,1,1]:raise RuntimeError('Set the starting pose first.')
                        name,busy,ready,_=self.audio_state()
                        if name!='READY' or busy or not ready:raise RuntimeError('Robot audio not ready; demo was not started.')
                        self.smooth(END,scene=data)
                        self.emit('phase','Final pose sent · allowing 0.5s to settle...');self.wait_until(time.monotonic()+SETTLE)
                        self.exchange('arm_live status')
                        if self.state['pulse'][:3]!=list(END) or self.state['base_spin']:raise RuntimeError('Final command state not confirmed. Hello was not started.')
                        self.hello();self.emit('finished','Greeting complete. End pose is holding; support the arm before Release all.')
                    elif kind=='sound':self.hello();self.emit('finished','Hello playback completed on the board. Listen to confirm audible quality.')
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

class GreetingDemo:
    def __init__(self,root):
        self.root=root;self.events=queue.Queue();self.link=DemoLink(lambda *e:self.events.put(e));self.connected=False;self.busy=False;self.closing=False;self.state=None
        root.title('Robot arm · Hello demo');root.geometry('770x660');root.minsize(740,640);root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam');style.configure('TButton',font=('Segoe UI',11),padding=(12,9));style.configure('TLabel',font=('Segoe UI',10))
        box=ttk.Frame(root,padding=20);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Hello, teammates!',font=('Segoe UI',23,'bold')).pack(anchor='w')
        ttk.Label(box,text='Smooth motion: 300µs per 0.5s · base turns for 1s · Hello at100% volume',wraplength=710).pack(anchor='w',pady=8)
        row=ttk.Frame(box);row.pack(fill='x',pady=5);self.connection=tk.StringVar(value='Not connected')
        ttk.Label(row,textvariable=self.connection).pack(side='left');self.connect_button=ttk.Button(row,text='Connect',command=self.connect);self.connect_button.pack(side='right')
        table=ttk.Frame(box);table.pack(fill='x',pady=8)
        for col,text in enumerate(('Joint','Start pulse','End pulse')):ttk.Label(table,text=text,font=('Segoe UI',11,'bold')).grid(row=0,column=col,sticky='w',padx=15,pady=5)
        for i,(name,start,end) in enumerate(zip(('Lift · GPIO12','Middle · GPIO10','End plate · GPIO11'),START,END),1):
            for col,text in enumerate((name,f'{start}µs',f'{end}µs')):ttk.Label(table,text=text).grid(row=i,column=col,sticky='w',padx=15,pady=4)
        row=ttk.Frame(box);row.pack(fill='x',pady=8);self.base_speed=tk.StringVar(value='5');self.neutral=tk.StringVar(value='1500');self.direction=tk.StringVar(value='Forward')
        ttk.Label(row,text='Base GPIO15:').pack(side='left');ttk.Combobox(row,textvariable=self.direction,state='readonly',values=('Forward','Reverse'),width=9).pack(side='left',padx=6)
        ttk.Label(row,text='speed %').pack(side='left');ttk.Spinbox(row,from_=1,to=100,textvariable=self.base_speed,width=5).pack(side='left',padx=6)
        ttk.Label(row,text='stop µs').pack(side='left');ttk.Spinbox(row,from_=1400,to=1600,textvariable=self.neutral,width=6).pack(side='left',padx=6)
        self.checked=tk.BooleanVar(value=False)
        ttk.Checkbutton(box,text='External servo power + common ground checked; arm/cables have clearance',variable=self.checked,command=self.check_changed).pack(anchor='w',pady=9)
        row=ttk.Frame(box);row.pack(fill='x',pady=5)
        self.prepare_button=ttk.Button(row,text='1 · Set starting pose…',command=self.prepare);self.prepare_button.pack(side='left',fill='x',expand=True,padx=(0,6))
        self.run_button=ttk.Button(row,text='2 · Run greeting',command=self.run);self.run_button.pack(side='left',fill='x',expand=True)
        row=ttk.Frame(box);row.pack(fill='x',pady=5)
        self.stop_button=ttk.Button(row,text='STOP demo / hold pose',command=self.stop);self.stop_button.pack(side='left',fill='x',expand=True,padx=(0,6))
        self.off_button=ttk.Button(row,text='Release all…',command=self.off);self.off_button.pack(side='left',fill='x',expand=True)
        self.sound_button=ttk.Button(box,text='Test robot Hello only',command=self.sound);self.sound_button.pack(anchor='w',pady=5)
        self.status=tk.StringVar(value='No automatic movement, microphone recording or sound. Close other controllers before connecting.')
        ttk.Label(box,textvariable=self.status,wraplength=710,font=('Segoe UI',11)).pack(anchor='w',pady=(12,8))
        ttk.Label(box,text='Initial engagement can move suddenly. Support/unload the arm if needed.\nAfterward, the end pose holds. Release/closing/power loss can let the arm fall.\nBase has no angle feedback: align its starting direction manually before each take.',wraplength=710,foreground='#555555').pack(anchor='w')
        self.refresh();root.after(60,self.poll)
    def refresh(self):
        ready=self.connected and self.checked.get() and not self.busy and not self.closing
        self.connect_button.configure(state='disabled' if self.busy or self.closing or (self.state and any(self.state['active'])) else 'normal')
        self.prepare_button.configure(state='normal' if ready else 'disabled')
        at_start=bool(self.state and self.state['pulse'][:3]==list(START) and self.state['active'][:3]==[1,1,1])
        self.run_button.configure(state='normal' if ready and at_start else 'disabled')
        self.sound_button.configure(state='normal' if self.connected and not self.busy and not self.closing else 'disabled')
        for b in (self.stop_button,self.off_button):b.configure(state='normal' if self.connected and not self.closing else 'disabled')
    def connect(self):
        if self.busy:return
        self.busy=True;self.checked.set(False);self.refresh();self.link.submit('connect')
    def check_changed(self):
        if not self.checked.get() and self.busy:self.stop()
        self.refresh()
    def prepare(self):
        if not(self.connected and self.checked.get() and not self.busy):return
        if not messagebox.askokcancel('Set starting pose',f'Move to lift1000 / middle600 / plate2500µs?\nInitial positions are not measured; first engagement can move suddenly. Confirm external power, common ground and clearance.',parent=self.root):return
        self.busy=True;self.refresh();self.link.submit('prepare')
    def run(self):
        if not(self.connected and self.checked.get() and not self.busy):return
        try:
            speed=int(self.base_speed.get());neutral=int(self.neutral.get())
            if not 1<=speed<=100 or not 1400<=neutral<=1600:raise ValueError()
        except ValueError:messagebox.showerror('Base settings','Use speed1–100% and neutral1400–1600µs.');return
        self.busy=True;self.refresh();self.link.submit('run',(speed,1 if self.direction.get()=='Forward' else -1,neutral))
    def sound(self):
        if self.connected and not self.busy:self.busy=True;self.refresh();self.link.submit('sound')
    def stop(self):
        if self.connected:self.busy=True;self.refresh();self.link.submit('stop')
    def off(self):
        if self.connected and messagebox.askokcancel('Support arm','Release all position signals? Support the arm so it cannot fall.',parent=self.root):self.busy=True;self.checked.set(False);self.refresh();self.link.submit('off')
    def poll(self):
        self.link.ui_alive=time.monotonic()
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='connected':
                    self.connected=True;self.busy=False;self.connection.set('Board ready · '+data[0]);self.status.set('Connected. Robot audio '+('ready.' if data[1][:3]==('READY',0,1) else 'not ready: '+str(data[1])))
                elif kind=='state':self.state=data
                elif kind=='phase':self.status.set(data)
                elif kind=='finished':self.busy=False;self.status.set(data)
                elif kind=='error':self.connected=False;self.busy=False;self.state=None;self.checked.set(False);self.connection.set('Disconnected');self.status.set(data)
                elif kind=='closed':self.root.destroy();return
                self.refresh()
        except queue.Empty:pass
        self.root.after(60,self.poll)
    def close(self):
        if self.closing:return
        if self.state and any(self.state['active']) and not messagebox.askokcancel('Support arm first','Closing stops sound and releases position signals. Support the arm first.',parent=self.root):return
        self.closing=True;self.refresh();self.link.submit('close')

if __name__=='__main__':
    root=tk.Tk();GreetingDemo(root);root.mainloop()
