"""Observed joint-travel calibration; uses the installed arm firmware."""
import json,pathlib,queue,time,tkinter as tk
from tkinter import ttk,messagebox
from arm_controller import Link,PINS,HERE

NAMES=('Bottom lift · MG90S · GPIO12','Middle joint · SG90 · GPIO10','End plate · SG90 · GPIO11')

def validate_profile(c):
    for k in ('down','up','start'):
        if c[k] is not None and (type(c[k]) is not int or not 500<=c[k]<=2500):raise ValueError('Invalid saved pulse')
    if c['down'] is not None and c['up'] is not None and abs(c['up']-c['down'])<20:raise ValueError('Endpoints must be at least 20µs apart.')
    return c

def percent(pulse,c):
    a,b=c['down'],c['up']
    if a is None or b is None or a==b:return None
    return 100*(pulse-a)/(b-a)

def step_target(pulse,c,direction,amount):
    fraction=percent(pulse,c)
    if fraction is None:raise ValueError('Save both endpoints first.')
    if not -.01<=fraction<=100.01:raise ValueError('Current command is outside saved travel. Use calibration to enter the range.')
    fraction=max(0,min(100,fraction+direction*amount))
    return round(c['down']+(c['up']-c['down'])*fraction/100)

class Calibration:
    def __init__(self,root):
        self.root=root;self.events=queue.Queue();self.link=Link(lambda *e:self.events.put(e))
        self.connected=False;self.busy=False;self.holding=False;self.closing=False;self.current=[None]*3;self.last_index=None;self.deadline=0
        self.profile=[{'down':None,'up':None,'start':None} for _ in PINS]
        try:
            saved=json.loads((HERE/'joint-calibration.json').read_text())
            if len(saved)!=3:raise ValueError('Three joints required')
            self.profile=[validate_profile(c) for c in saved]
        except (FileNotFoundError,ValueError,KeyError,TypeError):pass
        root.title('Arm Control — joint calibration');root.geometry('900x820');root.minsize(860,780);root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam');style.configure('TButton',font=('Segoe UI',10),padding=(9,6));style.configure('TLabel',font=('Segoe UI',10))
        box=ttk.Frame(root,padding=16);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Calibrate your arm',font=('Segoe UI',20,'bold')).pack(anchor='w')
        row=ttk.Frame(box);row.pack(fill='x',pady=5)
        self.connection=tk.StringVar(value='Not connected');ttk.Label(row,textvariable=self.connection).pack(side='left')
        self.connect_button=ttk.Button(row,text='Connect',command=self.connect);self.connect_button.pack(side='right')
        ttk.Label(box,text='Board 5V: power ONE unloaded servo at a time; disconnect the other two red wires.\nSupport the arm. Initial engagement can move it; a photo cannot reveal its current shaft position.',wraplength=830,foreground='#8c3a15').pack(anchor='w',pady=5)
        self.mode=tk.StringVar(value='Board 5V: one powered servo, brief pulses')
        self.selector=ttk.Combobox(box,textvariable=self.mode,state='readonly',values=('Board 5V: one powered servo, brief pulses','Separate servo supply: continuous holding'))
        self.selector.pack(fill='x');self.selector.bind('<<ComboboxSelected>>',self.mode_changed)
        self.armed=tk.BooleanVar(value=False)
        ttk.Checkbutton(box,text='Power matches selection; tested joint unloaded / arm supported; common ground connected',variable=self.armed,command=self.arm_changed).pack(anchor='w',pady=5)
        tabs=ttk.Notebook(box);tabs.pack(fill='both',expand=True)
        cal=ttk.Frame(tabs,padding=12);run=ttk.Frame(tabs,padding=12);guide=ttk.Frame(tabs,padding=12)
        tabs.add(cal,text='1 · Find joint travel');tabs.add(run,text='2 · Move calibrated joints');tabs.add(guide,text='How to calibrate')
        self.joint=tk.IntVar(value=0)
        for i,name in enumerate(NAMES):ttk.Radiobutton(cal,text=name,variable=self.joint,value=i,command=self.joint_changed).pack(anchor='w',pady=2)
        row=ttk.Frame(cal);row.pack(fill='x',pady=8)
        self.start=tk.StringVar(value='1500');ttk.Label(row,text='First engagement pulse (µs):').pack(side='left')
        self.start_entry=ttk.Entry(row,textvariable=self.start,width=8);self.start_entry.pack(side='left',padx=6)
        self.engage_button=ttk.Button(row,text='Engage selected joint…',command=self.engage);self.engage_button.pack(side='left',padx=6)
        ttk.Label(cal,text='1500µs is only a starting suggestion, not a known safe pose.\nFor first setup, loosen/remove the horn or linkage if a centre move could hit anything.',wraplength=800).pack(anchor='w')
        self.readout=tk.StringVar();ttk.Label(cal,textvariable=self.readout,font=('Segoe UI',14,'bold')).pack(anchor='w',pady=10)
        row=ttk.Frame(cal);row.pack(fill='x',pady=6)
        self.jog_step=tk.StringVar(value='5');ttk.Label(row,text='Pulse step (µs):').pack(side='left')
        ttk.Combobox(row,textvariable=self.jog_step,state='normal',values=('2','5','10','20','100','500','800'),width=8).pack(side='left',padx=8)
        self.minus=ttk.Button(row,text='− pulse',command=lambda:self.jog(-1));self.minus.pack(side='left',padx=5)
        self.plus=ttk.Button(row,text='+ pulse',command=lambda:self.jog(1));self.plus.pack(side='left',padx=5)
        self.expanded=tk.BooleanVar(value=False)
        ttk.Checkbutton(cal,text='Allow exploring beyond initial 1300–1700µs (unloaded, with clearance)',variable=self.expanded,command=self.refresh).pack(anchor='w',pady=5)
        row=ttk.Frame(cal);row.pack(fill='x',pady=7);self.mark_buttons=[]
        for key,label in (('down','Mark DOWN end · 0%'),('up','Mark UP end · 100%'),('start','Save starting pose')):
            b=ttk.Button(row,text=label,command=lambda k=key:self.mark(k));b.pack(side='left',padx=3);self.mark_buttons.append(b)
        self.endpoints=tk.StringVar();ttk.Label(cal,textvariable=self.endpoints,wraplength=800).pack(anchor='w',pady=5)
        ttk.Label(cal,text='Mark usable limits BEFORE contact, binding or buzzing—never push into the mechanical stop.\nDOWN / UP are your chosen directions. Saving them in reverse automatically reverses the arrows.',wraplength=800).pack(anchor='w')
        row=ttk.Frame(run);row.pack(fill='x',pady=4);self.travel_step=tk.StringVar(value='1')
        ttk.Label(row,text='Travel per click (%):').pack(side='left');ttk.Combobox(row,textvariable=self.travel_step,state='readonly',values=('1','2','5'),width=5).pack(side='left',padx=8)
        self.cards=[]
        for i,name in enumerate(NAMES):
            card=ttk.LabelFrame(run,text=name,padding=9);card.pack(fill='x',pady=8)
            row=ttk.Frame(card);row.pack(fill='x');text=tk.StringVar();ttk.Label(row,textvariable=text).pack(side='left',fill='x',expand=True)
            down=ttk.Button(row,text='↓',width=5,command=lambda j=i:self.travel(j,-1));down.pack(side='left',padx=4)
            up=ttk.Button(row,text='↑',width=5,command=lambda j=i:self.travel(j,1));up.pack(side='left',padx=4)
            engage=ttk.Button(row,text='Engage saved pose…',command=lambda j=i:self.engage_saved(j));engage.pack(side='left',padx=4)
            bar=ttk.Progressbar(card,maximum=100);bar.pack(fill='x',pady=6)
            detail=tk.StringVar();ttk.Label(card,textvariable=detail).pack(anchor='w');self.cards.append((text,detail,bar,down,up,engage))
        ttk.Label(run,text='Percentage is commanded travel between YOUR marked endpoints. It is not measured shaft angle.\nNo 180° claim: these joints may have less usable travel in this arm.',wraplength=800).pack(anchor='w',pady=10)
        instructions='1. Fix power first. Board-only bench test: disconnect the other two red servo wires and unload the selected joint. For a working arm that holds its pose, use a suitable separate regulated 5V servo supply with common ground.\n\n2. Choose the joint. For its first engagement, support/unload the arm and loosen the horn/linkage if necessary. Click Engage only when that initial move is clear. There is no position feedback to make this first move automatically gentle.\n\n3. Use 5µs pulse steps. Watch which direction it actually moves. If it only turns continuously, stop: it may be a continuous-rotation unit, which cannot be position-calibrated with this controller. If it buzzes, binds or cannot lift, stop and check load, power, linkage and servo torque. Do not increase pulse range to force it.\n\n4. Explore gradually. Mark a usable DOWN endpoint and UP endpoint, leaving clearance at both ends. Use 2µs for fine adjustment. Wider pulse exploration is explicitly unlocked; 500–2500µs are software bounds, not guaranteed safe servo limits.\n\n5. Jog to a convenient starting pose and save it BETWEEN those endpoints. Saves record your observations; software cannot verify a collision-free envelope for every combination of the other joints. Repeat each joint separately.\n\n6. In Move calibrated joints, engage the saved pose explicitly, then use arrows. Start at 1% travel per click. A brief test releases after 0.7s and can sag; continuous holding requires suitable separate power.\n\nSupport the arm before Release, closing, disconnecting or power loss. The existing board watchdog releases holds after about 5 seconds without host communication. Release is not a power switch or a mechanical brake.'
        ttk.Label(guide,text=instructions,wraplength=800,justify='left').pack(anchor='w')
        self.release_button=ttk.Button(box,text='RELEASE ALL — support the arm first',command=self.release);self.release_button.pack(fill='x',pady=(10,5))
        self.status=tk.StringVar(value='Connect when the earlier controller is closed. Nothing moves automatically.')
        ttk.Label(box,textvariable=self.status,wraplength=830).pack(anchor='w');self.refresh();root.after(80,self.poll)
    def hold(self):return self.mode.get().startswith('Separate')
    def can_move(self):return self.connected and self.armed.get() and not self.busy and not self.closing
    def connect(self):
        if self.busy or self.holding:return
        self.busy=True;self.current=[None]*3;self.armed.set(False);self.refresh();self.link.submit('connect')
    def mode_changed(self,event=None):self.armed.set(False);self.refresh()
    def arm_changed(self):
        if not self.armed.get() and self.connected:self.release()
        self.refresh()
    def joint_changed(self):
        c=self.profile[self.joint.get()];self.start.set(str(c['start'] or 1500));self.expanded.set(False);self.refresh()
    def refresh(self):
        ready=self.can_move();i=self.joint.get();p=self.current[i];c=self.profile[i]
        self.connection.set('Connected' if self.connected else 'Not connected')
        self.connect_button.configure(state='disabled' if self.busy or self.holding or self.closing else 'normal')
        self.selector.configure(state='disabled' if self.busy or self.holding else 'readonly')
        self.release_button.configure(state='normal' if self.connected and not self.closing else 'disabled')
        self.engage_button.configure(state='normal' if ready else 'disabled')
        self.start_entry.configure(state='disabled' if self.busy else 'normal')
        self.readout.set('No command sent to this joint' if p is None else f'Last command: {p}µs  ·  '+('holding' if self.holding else 'brief signal / position not measured'))
        lo,hi=(500,2500) if self.expanded.get() else (1300,1700)
        self.minus.configure(state='normal' if ready and p is not None and lo<p<=hi else 'disabled')
        self.plus.configure(state='normal' if ready and p is not None and lo<=p<hi else 'disabled')
        for b in self.mark_buttons:b.configure(state='normal' if ready and p is not None else 'disabled')
        self.endpoints.set(f"Saved: DOWN {c['down']}µs | UP {c['up']}µs | Start {c['start']}µs")
        for j,(text,detail,bar,down,up,engage) in enumerate(self.cards):
            cfg=self.profile[j];pulse=self.current[j];fraction=percent(pulse,cfg) if pulse is not None else None
            calibrated=cfg['down'] is not None and cfg['up'] is not None
            within=fraction is not None and 0<=fraction<=100
            text.set('Position unknown' if pulse is None else f'{pulse}µs · '+(f'{fraction:.1f}% of marked travel' if fraction is not None else 'not calibrated'))
            detail.set('Mark both travel ends first' if not calibrated else (f'Remaining ↓ {fraction:.1f}% / ↑ {100-fraction:.1f}%' if within else 'Engage a saved pose within calibrated travel'))
            bar['value']=max(0,min(100,fraction)) if fraction is not None else 0
            down.configure(state='normal' if ready and within and fraction>0 else 'disabled');up.configure(state='normal' if ready and within and fraction<100 else 'disabled')
            engage.configure(state='normal' if ready and calibrated and cfg['start'] is not None and min(cfg['down'],cfg['up'])<=cfg['start']<=max(cfg['down'],cfg['up']) else 'disabled')
    def send(self,index,pulse,initial=False):
        if not self.can_move():return
        if not 500<=pulse<=2500:messagebox.showerror('Pulse bounds','Pulse must stay within 500–2500µs.');return
        if not initial and self.current[index] is None:return
        if not self.hold():self.current=[None if j!=index else p for j,p in enumerate(self.current)]
        self.busy=True;self.status.set(f'Sending {pulse}µs to {NAMES[index]}');self.refresh();self.link.submit('pulse',(index,pulse,self.hold()))
    def confirm_engage(self,index,pulse):
        if not self.can_move():return
        if messagebox.askokcancel('First engagement can move suddenly',f'{NAMES[index]}\nSend {pulse}µs now?\nSupport/unload the arm. Remove the horn/linkage if clearance is uncertain. Current physical position is unknown.',parent=self.root):self.send(index,pulse,True)
    def engage(self):
        try:p=int(self.start.get())
        except ValueError:messagebox.showerror('Pulse','Enter an integer pulse in microseconds.');return
        lo,hi=(500,2500) if self.expanded.get() else (1300,1700)
        if not lo<=p<=hi:messagebox.showerror('Initial exploration bounds',f'Use {lo}–{hi}µs. Wider exploration must be unlocked explicitly.');return
        self.confirm_engage(self.joint.get(),p)
    def engage_saved(self,index):
        p=self.profile[index]['start']
        if p is not None:self.confirm_engage(index,p)
    def jog(self,direction):
        if not self.can_move():return
        i=self.joint.get();p=self.current[i]
        if p is None:return
        try:
            step=int(self.jog_step.get())
            if step<=0:raise ValueError()
        except ValueError:
            messagebox.showerror('Pulse step','Enter a positive whole number of microseconds, such as 5, 500 or 800.');return
        lo,hi=(500,2500) if self.expanded.get() else (1300,1700)
        target=max(lo,min(hi,p+direction*step))
        if target==p:return
        self.send(i,target)
    def mark(self,key):
        if not self.can_move():return
        i=self.joint.get();p=self.current[i]
        if p is None:return
        candidate=dict(self.profile[i],**{key:p})
        try:validate_profile(candidate)
        except ValueError as exc:messagebox.showerror('Calibration',str(exc));return
        if key=='start' and (candidate['down'] is None or candidate['up'] is None or not min(candidate['down'],candidate['up'])<=p<=max(candidate['down'],candidate['up'])):
            messagebox.showinfo('Mark limits first','Save both endpoints, then a starting pose between them.');return
        self.profile[i]=candidate;(HERE/'joint-calibration.json').write_text(json.dumps(self.profile,indent=2));self.status.set('Observed joint setting saved. No movement sent.');self.refresh()
    def travel(self,index,direction):
        if not self.can_move() or self.current[index] is None:return
        try:target=step_target(self.current[index],self.profile[index],direction,int(self.travel_step.get()))
        except ValueError as exc:messagebox.showinfo('Calibration',str(exc));return
        self.send(index,target)
    def release(self):
        if self.connected:self.busy=True;self.armed.set(False);self.deadline=0;self.refresh();self.link.submit('stop')
    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='connected':self.connected=True;self.busy=False;self.status.set('Connected. Select power setup; confirm wiring. No signals started.')
                elif kind=='pulsed':
                    i,p,hold=data;self.current[i]=p;self.holding=bool(hold);self.last_index=i
                    self.busy=not hold;self.deadline=0 if hold else time.monotonic()+.85
                    self.status.set('Command acknowledged; holding.' if hold else 'Brief pulse accepted; releasing after 0.7s. The joint may sag.')
                elif kind=='stopped':self.busy=False;self.holding=False;self.current=[None]*3;self.status.set('Signals released. Physical positions unknown.');self.deadline=0
                elif kind=='state' and self.holding and not data['lease']:
                    self.holding=False;self.current=[None]*3;self.armed.set(False);self.status.set('Hold expired; support the arm and reinitialize.')
                elif kind=='error':self.connected=False;self.busy=False;self.holding=False;self.current=[None]*3;self.armed.set(False);self.deadline=0;self.status.set(data)
                elif kind=='closed':self.root.destroy();return
                self.refresh()
        except queue.Empty:pass
        if self.deadline and time.monotonic()>=self.deadline:
            self.deadline=0;self.busy=False;self.status.set('Signal released. Last pulse remains a reference; physical position may have changed.');self.refresh()
        self.root.after(80,self.poll)
    def close(self):
        if self.closing:return
        if self.holding and not messagebox.askokcancel('Support arm before release','Closing releases the signals. Support the arm first.',parent=self.root):return
        self.closing=True;self.armed.set(False);self.refresh();self.link.submit('close')

if __name__=='__main__':
    root=tk.Tk();Calibration(root);root.mainloop()
