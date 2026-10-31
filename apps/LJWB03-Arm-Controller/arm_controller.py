"""Three-servo manual controller. No movement on launch; all angles are estimates."""
import os
import datetime,json,pathlib,queue,re,threading,time,tkinter as tk
from tkinter import ttk,messagebox
import serial
from serial.tools import list_ports

HERE=pathlib.Path(__file__).resolve().parent
PINS=(12,10,11)
NAMES=('MG90S','SG90 #1','SG90 #2')
STATUS=rb'ARM_STATUS version=1 session=(\d+) gpio=12,10,11 angles=(-?\d+),(-?\d+),(-?\d+) active=([01]),([01]),([01]) lease=([01])'

def board_port():
    found=[p.device for p in list_ports.comports() if (p.vid,p.pid)==(0x1a86,0x55d3) and (not os.environ.get('LJWB03_SERIAL') or p.serial_number==os.environ['LJWB03_SERIAL'])]
    if len(found)!=1:raise RuntimeError('Board not found. Connect its USB data cable and press Connect.')
    return found[0]

def parse_status(raw):
    m=re.search(STATUS,raw)
    if not m:raise RuntimeError('Expected three-servo firmware was not detected.')
    n=list(map(int,m.groups()));return {'session':n[0],'angles':n[1:4],'active':n[4:7],'lease':n[7]}

def move_command(index,angle,config,hold):
    if index not in range(3):raise ValueError('Invalid joint')
    if not(0<=config['min']<=angle<=config['max']<=180):raise ValueError('Joint limit reached')
    if not(500<=config['low']<=1500<=config['high']<=2500 and config['low']<config['high']):raise ValueError('Invalid pulse calibration')
    return f"arm_test move {PINS[index]} {angle} {config['low']} {config['high']} {int(hold)}"

def pulse_command(index,pulse,hold):
    """Encode a direct pulse with the installed CLI; no firmware change required.
    Internal 0/180 selects an endpoint; these values are NOT physical angles.
    """
    if index not in range(3) or type(pulse) is not int or not 500<=pulse<=2500:
        raise ValueError('Pulse must be an integer in 500..2500 microseconds.')
    angle,low,high=(0,pulse,2500) if pulse<=1500 else (180,500,pulse)
    return f'arm_test move {PINS[index]} {angle} {low} {high} {int(hold)}'

class Link:
    def __init__(self,emit):
        self.emit=emit;self.jobs=queue.PriorityQueue();self.counter=0;self.s=None;self.session=None
        threading.Thread(target=self.run,daemon=True).start()
    def submit(self,kind,data=None):
        if kind in ('stop','close'):
            while True:
                try:self.jobs.get_nowait()
                except queue.Empty:break
        self.counter+=1;self.jobs.put((0 if kind in ('stop','close') else 1,self.counter,kind,data))
    def exchange(self,command,expected):
        self.s.reset_input_buffer();self.s.write((command+'\r\n').encode());self.s.flush()
        raw=bytearray();end=time.monotonic()+2
        while time.monotonic()<end:
            raw.extend(self.s.read(2048))
            err=re.search(rb'ARM_ERROR[^\r\n]*',raw)
            if err:raise RuntimeError(err[0].decode(errors='replace'))
            if re.search(expected,raw):
                with (HERE/'commands.log').open('a',encoding='utf-8') as f:
                    f.write(datetime.datetime.now().isoformat()+' '+command+'\n'+raw.decode(errors='replace')+'\n')
                return bytes(raw)
        raise RuntimeError('Board reply timed out. Check power and close other serial apps.')
    def disconnect(self):
        if self.s:
            try:self.s.close()
            except Exception:pass
        self.s=None;self.session=None
    def run(self):
        while True:
            try:_,_,kind,data=self.jobs.get(timeout=1)
            except queue.Empty:
                if not self.s:continue
                kind,data='ping',None
            try:
                if kind=='connect':
                    self.disconnect();port=board_port()
                    self.s=serial.Serial(port=None,baudrate=115200,timeout=.06,rtscts=False,dsrdtr=False)
                    self.s.dtr=False;self.s.rts=False;self.s.port=port;self.s.open()
                    state=parse_status(self.exchange('arm_test status',STATUS));self.session=state['session']
                    if any(state['active']):raise RuntimeError('Outputs are active. Close the other controller and support the arm before reconnecting.')
                    self.emit('connected',port)
                elif kind in ('stop','close'):
                    if self.s:self.exchange('arm_test stop',rb'ARM_OK stop signals=OFF')
                    self.emit('stopped',None)
                    if kind=='close':self.disconnect();self.emit('closed',None);return
                elif not self.s:raise RuntimeError('Connect to the board first.')
                elif kind in ('move','pulse'):
                    if kind=='move':index,angle,config,hold=data
                    else:
                        index,pulse,hold=data
                        angle=0 if pulse<=1500 else 180
                    # Check session before every move; never use cached angles after board reboot.
                    state=parse_status(self.exchange('arm_test status',STATUS))
                    if state['session']!=self.session:raise RuntimeError('Board restarted. Reconnect; all position estimates must be initialized again.')
                    command=move_command(index,angle,config,hold) if kind=='move' else pulse_command(index,pulse,hold)
                    reply=self.exchange(command,f'ARM_OK move gpio={PINS[index]} angle={angle} pulse_us=\\d+ hold={int(hold)}'.encode())
                    if kind=='pulse' and not re.search(f'pulse_us={pulse} hold={int(hold)}'.encode(),reply):raise RuntimeError('Board acknowledged a different pulse; outputs released.')
                    self.emit('moved' if kind=='move' else 'pulsed',(index,angle if kind=='move' else pulse,hold))
                elif kind=='ping':
                    state=parse_status(self.exchange('arm_test ping',STATUS))
                    if state['session']!=self.session:raise RuntimeError('Board restarted. Reconnect and initialize positions again.')
                    self.emit('state',state)
            except Exception as exc:
                # A lost link also triggers the board's independent 5-second hold timeout.
                if self.s:
                    try:self.exchange('arm_test stop',rb'ARM_OK stop')
                    except Exception:pass
                self.disconnect();self.emit('error',str(exc))
                if kind=='close':self.emit('closed',None);return

class ArmController:
    def __init__(self,root):
        self.root=root;self.events=queue.Queue();self.link=Link(lambda *e:self.events.put(e))
        self.connected=False;self.busy=False;self.closing=False;self.angles=[None]*3;self.holding=False
        self.config=[{'min':60,'max':120,'low':1000,'high':2000} for _ in PINS]
        try:
            saved=json.loads((HERE/'settings.json').read_text())
            if len(saved)==3:
                for i,c in enumerate(saved):move_command(i,90,c,False)
                self.config=saved
        except Exception:pass
        root.title('LJWB03 Arm Control');root.geometry('780x790');root.minsize(760,760)
        root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam');style.configure('TButton',font=('Segoe UI',11),padding=(10,7));style.configure('TLabel',font=('Segoe UI',10))
        box=ttk.Frame(root,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Arm control',font=('Segoe UI',20,'bold')).pack(anchor='w')
        top=ttk.Frame(box);top.pack(fill='x',pady=6)
        self.connection=tk.StringVar(value='Connecting...');ttk.Label(top,textvariable=self.connection).pack(side='left')
        self.connect_button=ttk.Button(top,text='Connect',command=self.connect);self.connect_button.pack(side='right')
        tabs=ttk.Notebook(box);tabs.pack(fill='both',expand=True)
        control=ttk.Frame(tabs,padding=10);setup=ttk.Frame(tabs,padding=12)
        tabs.add(control,text='Move servos');tabs.add(setup,text='Wiring and limits')
        self.power=tk.StringVar(value='One powered servo: brief test')
        ttk.Label(control,text='Power setup').pack(anchor='w')
        self.mode=ttk.Combobox(control,textvariable=self.power,state='readonly',values=('One powered servo: brief test','Separate 5V supply: hold joints'))
        self.mode.pack(fill='x',pady=4);self.mode.bind('<<ComboboxSelected>>',self.mode_changed)
        self.checked=tk.BooleanVar(value=False)
        ttk.Checkbutton(control,text='Power matches selection; ground shared; arm supported and clear',variable=self.checked,command=self.check_changed).pack(anchor='w',pady=4)
        self.step=tk.IntVar(value=2);row=ttk.Frame(control);row.pack(fill='x',pady=4)
        ttk.Label(row,text='Degrees per click:').pack(side='left')
        ttk.Combobox(row,textvariable=self.step,values=(1,2,5,10),state='readonly',width=5).pack(side='left',padx=8)
        self.cards=[]
        for i,(name,pin) in enumerate(zip(NAMES,PINS)):
            card=ttk.LabelFrame(control,text=f'{name}  |  GPIO{pin}',padding=8);card.pack(fill='x',pady=5)
            r=ttk.Frame(card);r.pack(fill='x');label=tk.StringVar();ttk.Label(r,textvariable=label,width=46).pack(side='left',fill='x',expand=True)
            down=ttk.Button(r,text='↓',width=4,command=lambda j=i:self.move(j,-1));down.pack(side='left',padx=3)
            up=ttk.Button(r,text='↑',width=4,command=lambda j=i:self.move(j,1));up.pack(side='left',padx=3)
            center=ttk.Button(r,text='Start at 90°',command=lambda j=i:self.move(j,0));center.pack(side='left',padx=3)
            bar=ttk.Progressbar(card,maximum=180);bar.pack(fill='x',pady=(5,0))
            detail=tk.StringVar();ttk.Label(card,textvariable=detail,font=('Segoe UI',9)).pack(anchor='w')
            self.cards.append((label,detail,bar,down,up,center))
        self.stop_button=ttk.Button(control,text='RELEASE ALL — support the arm first',command=self.stop);self.stop_button.pack(fill='x',pady=10)
        self.status=tk.StringVar(value='No movement on launch. Initialize each powered servo explicitly at 90°.')
        ttk.Label(control,textvariable=self.status,wraplength=660).pack(anchor='w')
        ttk.Label(control,text='Angles are commanded estimates, not measured position.\nBrief mode releases after 0.7s; the joint may move under load.',foreground='#555555',wraplength=660).pack(anchor='w',pady=8)
        wiring='Signal wires (orange/yellow/white): MG90S → GPIO12; SG90 #1 → GPIO10; SG90 #2 → GPIO11.\n\nAll servo GND wires (brown/black) → common GND. Red wires → suitable regulated 5V servo supply. Join supply GND to board GND. Keep external +5V separate from board +5V while USB is connected.\n\nBoard-only test: connect power to ONE unloaded servo at a time; disconnect the other two red wires. Its red wire may use the board 5V pin for a brief test, but the available current is unverified. Stop if it resets, buzzes or heats. Do not run the loaded three-servo arm from unverified board power.\n\nCamera wiring stays unchanged (including PCLK GPIO9). Close the camera window while using arm controls.\n\nSupport the arm before Release, closing, unplugging, or loss of power. Signals also release if the controller stops communicating for 5 seconds.\n\nDefault limits: 60–120 on an estimated 0–180 scale. Pulse mapping starts at 1000–2000µs. This may cover less than 180° physically. Actual endpoints vary; expand gradually only with clearance. ↑ increases angle; physical direction depends on mounting.'
        ttk.Label(setup,text=wiring,wraplength=675,justify='left').pack(anchor='w')
        grid=ttk.Frame(setup);grid.pack(fill='x',pady=12)
        for j,t in enumerate(('Servo','Min °','Max °','0° pulse µs','180° pulse µs')):ttk.Label(grid,text=t).grid(row=0,column=j,padx=5)
        self.fields=[]
        for i,name in enumerate(NAMES):
            ttk.Label(grid,text=name).grid(row=i+1,column=0,padx=5,pady=4);fields={}
            for j,key in enumerate(('min','max','low','high'),1):
                var=tk.StringVar(value=str(self.config[i][key]));ttk.Entry(grid,textvariable=var,width=9).grid(row=i+1,column=j,padx=5);fields[key]=var
            self.fields.append(fields)
        ttk.Button(setup,text='Apply limits / calibration (signals must be released)',command=self.apply).pack(anchor='w')
        self.refresh();root.after(80,self.poll);root.after(200,self.connect)
    def hold(self):return self.power.get().startswith('Separate')
    def refresh(self):
        enabled=self.connected and self.checked.get() and not self.busy and not self.closing
        self.connect_button.configure(state='disabled' if self.busy or self.closing or self.holding else 'normal')
        self.mode.configure(state='disabled' if self.busy or self.holding else 'readonly')
        self.stop_button.configure(state='normal' if self.connected and not self.closing else 'disabled')
        for i,(label,detail,bar,down,up,center) in enumerate(self.cards):
            a=self.angles[i];c=self.config[i]
            label.set('Not initialized — position unknown' if a is None else f'Last command: {a}°   |   ↓ {a}° / ↑ {180-a}° on scale')
            detail.set(f"Limits {c['min']}–{c['max']}°"+(f"  |  within limits: ↓ {a-c['min']}° / ↑ {c['max']-a}°" if a is not None else '  |  Start at 90° may move the joint'))
            bar['value']=a if a is not None else 0
            down.configure(state='normal' if enabled and a is not None and a>c['min'] else 'disabled')
            up.configure(state='normal' if enabled and a is not None and a<c['max'] else 'disabled')
            center.configure(state='normal' if enabled else 'disabled')
    def connect(self):
        if self.busy or self.holding:return
        self.busy=True;self.checked.set(False);self.angles=[None]*3;self.refresh();self.link.submit('connect')
    def mode_changed(self,event=None):
        self.checked.set(False);self.refresh()
    def check_changed(self):
        if not self.checked.get() and self.connected:self.stop()
        self.refresh()
    def move(self,index,direction):
        if not(self.connected and self.checked.get() and not self.busy):return
        a=90 if direction==0 else self.angles[index]+direction*self.step.get()
        a=max(self.config[index]['min'],min(self.config[index]['max'],a))
        if direction==0 and not messagebox.askokcancel('Initialize joint',f'Support the arm. Move {NAMES[index]} to its estimated 90° position now?',parent=self.root):return
        self.busy=True;self.status.set(f'Sending {NAMES[index]} → {a}°...');self.refresh()
        self.link.submit('move',(index,a,self.config[index].copy(),self.hold()))
    def stop(self):
        if self.connected:self.busy=True;self.refresh();self.link.submit('stop')
    def apply(self):
        if self.busy or self.holding:messagebox.showinfo('Release first','Support the arm, release all signals, then edit limits.');return
        try:
            configs=[{k:int(v.get()) for k,v in fields.items()} for fields in self.fields]
            for i,c in enumerate(configs):
                if not 0<=c['min']<=90<=c['max']<=180:raise ValueError('Limits must include 90° and stay within 0–180°.')
                move_command(i,90,c,False)
            (HERE/'settings.json').write_text(json.dumps(configs,indent=2));self.config=configs;self.angles=[None]*3
            self.status.set('Settings saved. Initialize again; displayed degrees depend on calibration.');self.refresh()
        except Exception as exc:messagebox.showerror('Check settings',str(exc))
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='connected':self.connected=True;self.busy=False;self.connection.set('Board ready · '+value);self.status.set('Choose the actual power setup and check the box. No outputs started.')
                elif kind=='moved':
                    i,a,hold=value;self.angles[i]=a;self.holding=bool(hold)
                    if hold:self.busy=False;self.status.set('Position command accepted; joints hold while this window stays connected.')
                    else:self.status.set('Brief move accepted. Waiting for signal release...');self.root.after(850,self.finish_pulse)
                elif kind=='stopped':self.holding=False;self.busy=False;self.angles=[None]*3;self.checked.set(False);self.status.set('Signals released. Position is unknown; support the arm.')
                elif kind=='state':
                    if self.holding and not value['lease']:
                        self.holding=False;self.angles=[None]*3;self.checked.set(False);self.status.set('Hold expired. Signals released; reinitialize after checking power.')
                elif kind=='error':
                    self.connected=False;self.busy=False;self.holding=False;self.angles=[None]*3;self.checked.set(False);self.connection.set('Disconnected');self.status.set(value)
                elif kind=='closed':self.root.destroy();return
                self.refresh()
        except queue.Empty:pass
        self.root.after(80,self.poll)
    def finish_pulse(self):
        if self.closing or not self.connected or not self.checked.get():return
        self.busy=False;self.status.set('Signal released. Last command is shown; actual position is not measured.');self.refresh()
    def close(self):
        if self.closing:return
        if self.holding and not messagebox.askokcancel('Release arm','Support the arm before closing. Closing releases all servo signals.',parent=self.root):return
        self.closing=True;self.checked.set(False);self.refresh();self.link.submit('close')

if __name__=='__main__':
    root=tk.Tk();ArmController(root);root.mainloop()
