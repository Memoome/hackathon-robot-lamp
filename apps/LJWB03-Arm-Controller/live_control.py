"""Four-servo hold-to-move interface. Requires arm_live v1 firmware."""
import datetime,json,pathlib,queue,re,threading,time,tkinter as tk
from tkinter import ttk,messagebox
import serial
from arm_controller import board_port,HERE

PINS=(12,10,11,15)
NAMES=('Lift · MG90S · GPIO12','Middle · SG90 · GPIO10','End plate · SG90 · GPIO11')
STATUS=rb'LIVE_STATUS version=1 session=(\d+) gpio=12,10,11,15 pulse=(\d+),(\d+),(\d+),(\d+) active=([01]),([01]),([01]),([01]) moving=([01]),([01]),([01]),([01]) base_spin=([01]) lease=([01])'

def parse_status(raw):
    m=re.search(STATUS,raw)
    if not m:raise RuntimeError('Four-servo firmware not detected.')
    a=list(map(int,m.groups()));return dict(session=a[0],pulse=a[1:5],active=a[5:9],moving=a[9:13],base_spin=a[13],lease=a[14])

def base_command(direction,percent,neutral):
    if direction not in (-1,0,1) or not 0<=percent<=100 or not 1400<=neutral<=1600:raise ValueError('Invalid base speed or neutral.')
    offset=round((neutral-500 if direction<0 else 2500-neutral)*percent/100) if direction else 0
    return f'arm_live base {1 if direction<0 else 2 if direction>0 else 0} {offset} {neutral}'

class LiveLink:
    def __init__(self,emit):
        self.emit=emit;self.jobs=queue.Queue();self.lock=threading.Lock();self.intent=None;self.freeze_pending=False;self.ui_until=0
        self.s=None;self.session=None;self.last_poll=0
        threading.Thread(target=self.run,daemon=True).start()
    def submit(self,kind,data=None):
        if kind in ('off','close'):self.motion(None)
        self.jobs.put((kind,data))
    def motion(self,intent):
        with self.lock:
            self.intent=intent;self.ui_until=time.monotonic()+.3
            if intent is None:self.freeze_pending=True
    def ui_heartbeat(self):
        with self.lock:self.ui_until=time.monotonic()+.3
    def snapshot(self):
        with self.lock:
            if self.intent is not None and time.monotonic()>self.ui_until:
                self.intent=None;self.freeze_pending=True;self.emit('released','UI heartbeat stopped')
            intent=self.intent;freeze=self.freeze_pending;self.freeze_pending=False
        return intent,freeze
    def exchange(self,command):
        self.s.reset_input_buffer();self.s.write((command+'\r\n').encode());self.s.flush()
        raw=bytearray();until=time.monotonic()+1.2
        while time.monotonic()<until:
            raw.extend(self.s.read(2048))
            err=re.search(rb'LIVE_ERROR[^\r\n]*',raw)
            if err:raise RuntimeError(err[0].decode(errors='replace'))
            if re.search(STATUS,raw):
                state=parse_status(raw)
                with (HERE/'live-commands.log').open('a',encoding='utf-8') as f:f.write(datetime.datetime.now().isoformat()+' '+command+'\n'+raw.decode(errors='replace')+'\n')
                if self.session is not None and state['session']!=self.session:raise RuntimeError('Board restarted. Reconnect and engage joints again.')
                self.emit('state',state);return state
        raise RuntimeError('Board reply timed out. Check power and USB; close other serial apps.')
    def run(self):
        while True:
            kind=None
            try:
                intent,freeze=self.snapshot()
                if freeze and self.s:self.exchange('arm_live freeze')
                try:kind,data=self.jobs.get(timeout=.025)
                except queue.Empty:kind=None
                if kind=='connect':
                    if self.s:self.s.close()
                    self.session=None;port=board_port()
                    self.s=serial.Serial(port=None,baudrate=115200,timeout=.025,rtscts=False,dsrdtr=False)
                    self.s.dtr=False;self.s.rts=False;self.s.port=port;self.s.open()
                    state=self.exchange('arm_live status');self.session=state['session']
                    if any(state['active']):raise RuntimeError('Outputs active. Close the earlier controller with the arm supported, then reconnect.')
                    self.emit('connected',port)
                elif kind in ('off','close'):
                    if self.s:self.exchange('arm_live off')
                    self.emit('off',None)
                    if kind=='close':
                        if self.s:self.s.close()
                        self.emit('closed',None);return
                elif kind=='engage':
                    i,pulse,mode=data
                    if not(i in range(3) and 500<=pulse<=2500 and mode in (0,1)):raise ValueError('Invalid starting pulse')
                    self.exchange(f'arm_live engage {PINS[i]} {pulse} {mode}');self.emit('engaged',i)
                elif kind=='neutral':
                    self.exchange(base_command(0,0,data));self.emit('engaged',3)
                elif kind is None and self.s:
                    # Re-read after queued commands: a mouse release cannot leave a stale jog queued.
                    intent,freeze=self.snapshot()
                    if freeze:self.exchange('arm_live freeze');intent=None
                    if intent:
                        if intent[0]=='joint':
                            _,i,direction,speed,mode=intent
                            self.exchange(f'arm_live jog {PINS[i]} {int(direction>0)} {speed} 500 2500 {mode}')
                        else:
                            _,direction,percent,neutral=intent;self.exchange(base_command(direction,percent,neutral))
                        self.last_poll=time.monotonic()
                    elif time.monotonic()-self.last_poll>.45:
                        self.exchange('arm_live ping');self.last_poll=time.monotonic()
            except Exception as exc:
                self.motion(None)
                if self.s and kind!='connect':
                    try:self.exchange('arm_live off')
                    except Exception:pass
                if self.s:
                    self.s.close()
                self.s=None;self.session=None;self.emit('error',str(exc))
                if kind=='close':self.emit('closed',None);return

class LiveControl:
    def __init__(self,root):
        self.root=root;self.events=queue.Queue();self.link=LiveLink(lambda *e:self.events.put(e))
        self.connected=False;self.busy=False;self.closing=False;self.pressed=None;self.state=None;self.port=''
        self.starts=[1500,1500,1500]
        try:
            cfg=json.loads((HERE/'joint-calibration.json').read_text())
            for i in range(3):
                p=cfg[i].get('start')
                if type(p) is int and 500<=p<=2500:self.starts[i]=p
        except (OSError,ValueError,KeyError,IndexError,TypeError):pass
        root.title('Arm Control — hold to move');root.geometry('860x850');root.minsize(820,820);root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam');style.configure('TButton',font=('Segoe UI',11),padding=(10,8));style.configure('TLabel',font=('Segoe UI',10))
        box=ttk.Frame(root,padding=16);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Hold to move the arm',font=('Segoe UI',20,'bold')).pack(anchor='w')
        row=ttk.Frame(box);row.pack(fill='x',pady=5)
        self.connection=tk.StringVar(value='Not connected');ttk.Label(row,textvariable=self.connection).pack(side='left')
        self.connect_button=ttk.Button(row,text='Connect',command=self.connect);self.connect_button.pack(side='right')
        self.mode=tk.StringVar(value='Board 5V bench: ONE powered, unloaded servo')
        self.power=ttk.Combobox(box,textvariable=self.mode,state='readonly',values=('Board 5V bench: ONE powered, unloaded servo','Separate regulated servo supply: hold joints'))
        self.power.pack(fill='x',pady=3);self.power.bind('<<ComboboxSelected>>',self.mode_changed)
        self.armed=tk.BooleanVar(value=False)
        ttk.Checkbutton(box,text='Power matches selection; common ground; arm supported and travel clear',variable=self.armed,command=self.arm_changed).pack(anchor='w',pady=4)
        tabs=ttk.Notebook(box);tabs.pack(fill='both',expand=True)
        control=ttk.Frame(tabs,padding=10);setup=ttk.Frame(tabs,padding=12);tabs.add(control,text='Move');tabs.add(setup,text='Starting poses / wiring')
        row=ttk.Frame(control);row.pack(fill='x',pady=4)
        self.speed=tk.IntVar(value=100);ttk.Label(row,text='Joint target speed (µs / second):').pack(side='left')
        ttk.Combobox(row,textvariable=self.speed,state='readonly',values=(25,50,100,200,400,600),width=6).pack(side='left',padx=8)
        ttk.Label(row,text='Lower = slower').pack(side='left')
        self.cards=[];self.motion_buttons=[]
        for i,name in enumerate(NAMES):
            card=ttk.LabelFrame(control,text=name,padding=8);card.pack(fill='x',pady=5)
            row=ttk.Frame(card);row.pack(fill='x');text=tk.StringVar();ttk.Label(row,textvariable=text,width=40).pack(side='left',fill='x',expand=True)
            down=ttk.Button(row,text='↓ Hold',width=9);down.pack(side='left',padx=3)
            up=ttk.Button(row,text='↑ Hold',width=9);up.pack(side='left',padx=3)
            engage=ttk.Button(row,text='Engage…',command=lambda j=i:self.engage(j));engage.pack(side='left',padx=3)
            self.bind_hold(down,('joint',i,-1));self.bind_hold(up,('joint',i,1))
            bar=ttk.Progressbar(card,maximum=2000);bar.pack(fill='x',pady=5)
            detail=tk.StringVar();ttk.Label(card,textvariable=detail,font=('Segoe UI',9)).pack(anchor='w');self.cards.append((text,detail,bar,down,up,engage))
        base=ttk.LabelFrame(control,text='Base · continuous MG90S · GPIO15',padding=9);base.pack(fill='x',pady=6)
        row=ttk.Frame(base);row.pack(fill='x')
        self.base_speed=tk.IntVar(value=5);ttk.Label(row,text='Base speed command (%):').pack(side='left')
        ttk.Combobox(row,textvariable=self.base_speed,state='readonly',values=(1,2,5,10,20,40,60,80,100),width=5).pack(side='left',padx=8)
        self.left=ttk.Button(row,text='← Hold');self.left.pack(side='left',padx=5);self.bind_hold(self.left,('base',-1))
        self.right=ttk.Button(row,text='Hold →');self.right.pack(side='left',padx=5);self.bind_hold(self.right,('base',1))
        row=ttk.Frame(base);row.pack(fill='x',pady=(7,0));self.neutral=tk.StringVar(value='1500')
        ttk.Label(row,text='Stop neutral (µs):').pack(side='left');self.neutral_entry=ttk.Entry(row,textvariable=self.neutral,width=7);self.neutral_entry.pack(side='left',padx=7)
        self.neutral_button=ttk.Button(row,text='Test stop neutral',command=self.test_neutral);self.neutral_button.pack(side='left')
        self.base_text=tk.StringVar(value='No angle feedback. Watch cable twist.');ttk.Label(base,textvariable=self.base_text,wraplength=740).pack(anchor='w',pady=4)
        row=ttk.Frame(control);row.pack(fill='x',pady=(8,4))
        self.freeze_button=ttk.Button(row,text='STOP motion / hold pose',command=self.stop);self.freeze_button.pack(side='left',fill='x',expand=True,padx=(0,5))
        self.off_button=ttk.Button(row,text='RELEASE ALL (support arm)',command=self.off);self.off_button.pack(side='left',fill='x',expand=True)
        ttk.Label(control,text='Release an arrow to freeze its target. Base receives neutral to stop.\nBoard bench mode releases the position signal after 0.7s; separate-supply mode holds.',wraplength=750).pack(anchor='w',pady=6)
        self.start_vars=[];self.reverse=[]
        ttk.Label(setup,text='Initial engagement is explicit and can move suddenly: current physical positions are unknown.\nUnload/support the arm; remove the horn/linkage first if clearance is uncertain.',wraplength=760).pack(anchor='w',pady=6)
        for i,name in enumerate(NAMES):
            row=ttk.Frame(setup);row.pack(fill='x',pady=7)
            ttk.Label(row,text=name,width=34).pack(side='left');var=tk.StringVar(value=str(self.starts[i]));self.start_vars.append(var)
            ttk.Entry(row,textvariable=var,width=7).pack(side='left',padx=5)
            ttk.Label(row,text='µs (500–2500)').pack(side='left');reverse=tk.BooleanVar(value=False);self.reverse.append(reverse)
            ttk.Checkbutton(row,text='Reverse arrows',variable=reverse).pack(side='left',padx=10)
        instructions='Position joints: signal GPIO12 (lift), GPIO10 (middle), GPIO11 (end plate). New continuous base: signal GPIO15. All grounds must be connected. Servo red wires need a suitable regulated 5V supply; keep external +5V separate from the USB-powered board +5V.\n\nBoard 5V current capacity is unverified. Bench mode is ONLY for one powered, unloaded servo at a time: disconnect the other red power wires. It cannot make four loaded servos safe on that supply. Use a suitable separate supply for the working arm.\n\nCamera wiring remains unchanged, including PCLK GPIO9. Close camera/calibration/older controller windows before connecting; they share the serial port.\n\nPosition limits are 500–2500µs, as requested. The speed setting controls how quickly the target changes, not measured shaft speed. Pulse/percentage displays are last commands, not position feedback.\n\nBase: 500µs reverse maximum, about 1500µs stopped, 2500µs forward maximum (user-confirmed). Speed percentage is command strength, not measured RPM. Adjust neutral a few µs if it creeps; Test stop neutral sends a brief pulse only when clicked. This servo cannot hold a selected angle. Watch wires; no automatic cable-twist limit exists.\n\nPress only one arrow at a time. Leaving the window, releasing the mouse or pressing STOP cancels motion. Board motion commands expire after 400ms without renewal. Holding position also expires after 5s without host contact. Support the arm before closing, release, unplugging or loss of power; it can fall.'
        ttk.Label(setup,text=instructions,wraplength=760,justify='left').pack(anchor='w',pady=10)
        self.status=tk.StringVar(value='Connect after closing older controllers. No signals start on launch.')
        ttk.Label(box,textvariable=self.status,wraplength=800).pack(anchor='w',pady=(7,0))
        root.bind_all('<ButtonRelease-1>',self.stop,add='+');root.bind('<FocusOut>',self.focus_out,add='+');root.bind('<Unmap>',self.stop,add='+')
        self.refresh();root.after(60,self.poll)
    def hold(self):return self.mode.get().startswith('Separate')
    def enabled(self):return self.connected and self.armed.get() and not self.busy and not self.closing
    def bind_hold(self,button,action):
        self.motion_buttons.append(button);button.bind('<ButtonPress-1>',lambda e:self.press(button,action))
    def connect(self):
        if self.busy or (self.state and any(self.state['active'])):return
        self.stop();self.busy=True;self.armed.set(False);self.refresh();self.link.submit('connect')
    def mode_changed(self,event=None):
        self.armed.set(False);self.off()
    def arm_changed(self):
        if not self.armed.get():self.off()
        self.refresh()
    def neutral_value(self):
        n=int(self.neutral.get())
        if not 1400<=n<=1600:raise ValueError('Stop neutral must be 1400–1600µs.')
        return n
    def engage(self,index):
        if not self.enabled() or self.pressed:return
        try:
            pulse=int(self.start_vars[index].get())
            if not 500<=pulse<=2500:raise ValueError('Starting pulse must be 500–2500µs.')
        except ValueError as exc:messagebox.showerror('Starting pulse',str(exc));return
        if not messagebox.askokcancel('Engage joint',f'Support/unload {NAMES[index]}.\nEngage at {pulse}µs? This first move can be sudden because its current position is unknown.',parent=self.root):return
        self.busy=True;self.refresh();self.link.submit('engage',(index,pulse,int(self.hold())))
    def test_neutral(self):
        if not self.enabled() or self.pressed:return
        try:n=self.neutral_value()
        except ValueError as exc:messagebox.showerror('Neutral',str(exc));return
        self.busy=True;self.refresh();self.link.submit('neutral',n)
    def press(self,button,action):
        if str(button['state'])=='disabled' or not self.enabled() or self.pressed:return
        if action[0]=='joint':
            _,i,d=action
            if not self.state or not self.state['pulse'][i]:return
            if self.reverse[i].get():d=-d
            intent=('joint',i,d,self.speed.get(),int(self.hold()))
        else:
            try:n=self.neutral_value()
            except ValueError as exc:messagebox.showerror('Neutral',str(exc));return
            intent=('base',action[1],self.base_speed.get(),n)
        self.pressed=action
        try:button.grab_set()
        except tk.TclError:pass
        self.link.motion(intent);self.status.set('Moving while held. Release to stop the target.');self.refresh()
    def stop(self,event=None):
        if event is None and self.connected:self.link.motion(None)
        if self.pressed:
            self.pressed=None;self.link.motion(None)
            try:
                grab=self.root.grab_current()
                if grab:grab.grab_release()
            except tk.TclError:pass
            self.status.set('Motion stop requested; position joints keep their current target in hold mode.');self.refresh()
    def focus_out(self,event=None):self.root.after_idle(self.check_focus)
    def check_focus(self):
        try:
            if self.root.focus_get() is None:self.stop()
        except tk.TclError:pass
    def off(self):
        self.stop();self.armed.set(False)
        if self.connected:self.busy=True;self.link.submit('off')
        self.refresh()
    def refresh(self):
        ready=self.enabled();state=self.state
        active=bool(state and any(state['active']))
        self.connect_button.configure(state='disabled' if self.busy or active or self.closing else 'normal')
        self.power.configure(state='disabled' if active or self.pressed else 'readonly')
        for i,(text,detail,bar,down,up,engage) in enumerate(self.cards):
            p=state['pulse'][i] if state else 0
            text.set(f'Last target: {p}µs' if p else 'Not engaged / position unknown')
            bar['value']=max(0,p-500)
            detail.set(f'Remaining pulse range: − {p-500}µs / + {2500-p}µs' if p else 'Engage explicitly before holding an arrow')
            for button,d in ((down,-1),(up,1)):
                d=-d if self.reverse[i].get() else d
                allowed=ready and p and (p>500 if d<0 else p<2500) and (self.pressed is None or self.pressed[0:2]==('joint',i))
                button.configure(state='normal' if allowed else 'disabled')
            engage.configure(state='normal' if ready and not self.pressed else 'disabled')
        for button in (self.left,self.right):button.configure(state='normal' if ready and (self.pressed is None or self.pressed[0]=='base') else 'disabled')
        self.neutral_entry.configure(state='disabled' if self.pressed else 'normal');self.neutral_button.configure(state='normal' if ready and not self.pressed else 'disabled')
        self.freeze_button.configure(state='normal' if self.connected else 'disabled');self.off_button.configure(state='normal' if self.connected else 'disabled')
        if state:
            self.base_text.set(f"Base command: {state['pulse'][3]}µs. No angle/twist feedback." if state['pulse'][3] else 'Base signal off. No angle feedback; watch cable twist.')
    def poll(self):
        if self.pressed:self.link.ui_heartbeat()
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='state':
                    self.state=value
                    if self.pressed and self.pressed[0]=='joint':
                        i=self.pressed[1];p=value['pulse'][i]
                        direction=self.pressed[2]*(-1 if self.reverse[i].get() else 1)
                        if not p or (p==500 and direction<0) or (p==2500 and direction>0):self.stop()
                elif kind=='connected':self.connected=True;self.busy=False;self.port=value;self.connection.set('Board ready · '+value);self.status.set('Select actual power setup and check the box. No joints engaged.')
                elif kind=='engaged':self.busy=False;self.status.set('Command accepted. Hold an arrow to move slowly.' if value!=3 else 'Brief neutral sent. Observe whether the base stops; adjust neutral if needed.')
                elif kind=='released':self.stop();self.status.set(value)
                elif kind=='off':self.busy=False;self.status.set('Signals released. Support the arm; positions are unknown.')
                elif kind=='error':self.stop();self.connected=False;self.busy=False;self.state=None;self.armed.set(False);self.connection.set('Disconnected');self.status.set(value)
                elif kind=='closed':self.root.destroy();return
                self.refresh()
        except queue.Empty:pass
        self.root.after(60,self.poll)
    def close(self):
        if self.closing:return
        self.stop()
        if self.state and any(self.state['active']) and not messagebox.askokcancel('Support arm first','Closing releases position signals. Support the arm before continuing.',parent=self.root):return
        self.closing=True;self.armed.set(False);self.refresh();self.link.submit('close')

if __name__=='__main__':
    root=tk.Tk();LiveControl(root);root.mainloop()
