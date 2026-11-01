"""Command-only tester for GPIO12 MG90S, GPIO10 SG90, GPIO13 motor module."""
import os
import datetime
import pathlib
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import serial
from serial.tools import list_ports

HERE=pathlib.Path(__file__).resolve().parent
SERIAL=os.environ.get('LJWB03_SERIAL','')
BG='#f4f6f8'
INK='#182b3a'
TEAL='#087f78'

def find_board():
    found=[p.device for p in list_ports.comports() if (p.vid,p.pid)==(0x1a86,0x55d3) and (not SERIAL or p.serial_number==SERIAL)]
    if len(found)!=1:raise RuntimeError('Board not found. Connect the USB data cable and click Connect.')
    return found[0]

def validate_status(raw):
    m=re.search(rb'ACT_STATUS version=1 ready=1 mg_gpio=12 sg_gpio=10 motor_gpio=13 motor_driver=([01]) mg_active=([01]) sg_active=([01]) motor_active=([01])',raw)
    if not m:raise RuntimeError('The board did not report the expected component-test firmware and pin mapping.')
    return tuple(int(x) for x in m.groups())

class BoardLink:
    def __init__(self,emit):
        self.emit=emit
        self.jobs=queue.PriorityQueue()
        self.counter=0
        self.serial=None
        self.port=None
        self.closing=False
        self.log=[]
        threading.Thread(target=self.worker,daemon=True).start()

    def submit(self,kind,command='',priority=1):
        if kind in ('stop','close'):
            # Cancel queued movements so they cannot execute after Stop.
            while True:
                try:self.jobs.get_nowait()
                except queue.Empty:break
        self.counter+=1
        self.jobs.put((priority,self.counter,kind,command))

    def exchange(self,command,expect,timeout=4):
        self.serial.reset_input_buffer()
        self.serial.write((command+'\r\n').encode('ascii'))
        self.serial.flush()
        raw=bytearray()
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            raw.extend(self.serial.read(4096))
            error=re.search(rb'ACT_ERROR[^\r\n]*',raw)
            if error:raise RuntimeError(error.group().decode('ascii',errors='replace'))
            if re.search(expect,raw):
                self.log.append({'time':datetime.datetime.now().isoformat(),'command':command,'response':raw.decode('utf-8',errors='replace')})
                return bytes(raw)
        raise RuntimeError('No component-test reply. Close other serial monitors, then reconnect.')

    def open(self):
        if self.serial:self.serial.close()
        self.port=find_board()
        s=serial.Serial(port=None,baudrate=921600,timeout=.08,rtscts=False,dsrdtr=False,xonxoff=False)
        s.dtr=False;s.rts=False;s.port=self.port;s.open()
        self.serial=s
        state=validate_status(self.exchange('act_test status',rb'ACT_STATUS[^\r\n]*motor_active=[01]'))
        return state

    def worker(self):
        while True:
            _,_,kind,command=self.jobs.get()
            try:
                if kind=='connect':
                    state=self.open();self.emit('connected',(self.port,state))
                elif kind=='close':
                    if self.serial:
                        try:self.exchange('act_test stop',rb'ACT_OK action=stop',timeout=1)
                        except Exception:pass
                        self.serial.close()
                    if self.log:
                        folder=HERE/'logs';folder.mkdir(exist_ok=True)
                        (folder/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')).write_text(__import__('json').dumps(self.log,indent=2),encoding='utf-8')
                    self.emit('closed',None);return
                elif not self.serial:
                    raise RuntimeError('Connect to the board first.')
                elif kind=='status':
                    state=validate_status(self.exchange('act_test status',rb'ACT_STATUS[^\r\n]*motor_active=[01]'))
                    self.emit('status',state)
                else:
                    action='stop' if kind=='stop' else 'servo' if kind=='servo' else 'motor'
                    self.exchange(command,('ACT_OK action='+action).encode())
                    self.emit('accepted',kind)
            except Exception as exc:
                if self.serial:
                    try:self.serial.close()
                    except Exception:pass
                self.serial=None
                self.emit('error',str(exc))

class ComponentTester:
    def __init__(self,root):
        self.root=root
        self.events=queue.Queue()
        self.link=BoardLink(lambda *event:self.events.put(event))
        self.connected=False;self.busy=False;self.closed=False;self.motor_driver=False
        self.buttons=[]
        root.title('LJWB03 Component Test')
        root.geometry('660x720');root.minsize(640,680);root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('TFrame',background=BG)
        style.configure('TLabel',background=BG,foreground=INK,font=('Segoe UI',10))
        style.configure('TButton',font=('Segoe UI',10),padding=(12,7))
        style.configure('TCheckbutton',background=BG,font=('Segoe UI',10))
        style.configure('TLabelframe',background=BG)
        style.configure('TLabelframe.Label',background=BG,foreground=INK,font=('Segoe UI',11,'bold'))
        style.configure('Stop.TButton',foreground='#a02121',font=('Segoe UI',11,'bold'))
        box=ttk.Frame(root,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Test your components',font=('Segoe UI',18,'bold')).pack(anchor='w')
        top=ttk.Frame(box);top.pack(fill='x',pady=(8,6))
        self.connection=tk.StringVar(value='Connecting...')
        ttk.Label(top,textvariable=self.connection).pack(side='left')
        self.connect_button=ttk.Button(top,text='Connect',command=self.connect)
        self.connect_button.pack(side='right')
        ttk.Label(box,text='VCC → suitable 5V supply. All grounds connected.\nGPIO12 / GPIO10 → servo signals. GPIO13 → module IN.',foreground='#566575',wraplength=590).pack(anchor='w')
        self.armed=tk.BooleanVar(value=False)
        ttk.Checkbutton(box,text='5V / common ground checked; servo arms have room to move',variable=self.armed,command=self.arm_changed).pack(anchor='w',pady=(9,5))
        for name,pin in [('MG90S',12),('SG90',10)]:
            card=ttk.LabelFrame(box,text=f'{name} servo · GPIO{pin}',padding=10)
            card.pack(fill='x',pady=5)
            row=ttk.Frame(card);row.pack(fill='x')
            for label,pulse in [('Left',1300),('Center',1500),('Right',1700)]:
                button=ttk.Button(row,text=label,command=lambda p=pin,u=pulse:self.servo(p,u))
                button.pack(side='left',expand=True,fill='x',padx=4)
                self.buttons.append(button)
        motor=ttk.LabelFrame(box,text='Vibration module · GPIO13',padding=10)
        motor.pack(fill='x',pady=5)
        row=ttk.Frame(motor);row.pack(fill='x')
        self.strength=tk.DoubleVar(value=100)
        self.strength_text=tk.StringVar(value='Strength: 100%')
        ttk.Label(row,textvariable=self.strength_text).pack(side='left')
        ttk.Scale(row,from_=10,to=100,variable=self.strength,command=lambda v:self.strength_text.set(f'Strength: {float(v):.0f}%')).pack(side='left',fill='x',expand=True,padx=12)
        self.motor_button=ttk.Button(row,text='Vibrate 0.25s',command=self.motor)
        self.motor_button.pack(side='right')
        self.stop_button=ttk.Button(box,text='STOP / release all',style='Stop.TButton',command=self.stop)
        self.stop_button.pack(fill='x',pady=(9,6))
        self.status=tk.StringVar(value='Nothing moves until you check the box and press a test button.')
        ttk.Label(box,textvariable=self.status,wraplength=590).pack(anchor='w')
        ttk.Label(box,text='Each click is brief. Servo signals release after 0.5s.\nLeft / Center / Right are test positions, not calibrated angles.',foreground='#566575',font=('Segoe UI',9),wraplength=590).pack(anchor='w',pady=(9,0))
        self.refresh();root.after(80,self.poll);root.after(200,self.connect)

    def refresh(self):
        enabled=self.connected and self.armed.get() and not self.busy
        for button in self.buttons:button.configure(state='normal' if enabled else 'disabled')
        self.motor_button.configure(state='normal' if enabled and self.motor_driver else 'disabled')
        self.stop_button.configure(state='normal' if self.connected else 'disabled')
        self.connect_button.configure(state='disabled' if self.busy else 'normal')

    def connect(self):
        if self.busy:return
        self.busy=True;self.refresh();self.connection.set('Connecting...')
        self.link.submit('connect')

    def arm_changed(self):
        if not self.armed.get() and self.connected:self.stop()
        self.refresh()

    def servo(self,pin,pulse):
        if not(self.connected and self.armed.get() and not self.busy):return
        self.busy=True;self.refresh()
        self.status.set(f'Sending a brief move to GPIO{pin}...')
        self.link.submit('servo',f'act_test servo {pin} {pulse} 500')

    def motor(self):
        if not(self.connected and self.armed.get() and not self.busy and self.motor_driver):return
        self.busy=True;self.refresh()
        self.link.submit('motor',f'act_test motor {round(self.strength.get())} 250')

    def stop(self):
        if self.connected:
            self.busy=True;self.refresh();self.link.submit('stop','act_test stop',priority=0)

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='connected':
                    self.connected=True;self.busy=False;self.motor_driver=bool(value[1][0])
                    self.connection.set(f'Board ready · {value[0]}')
                    self.status.set('Check the wiring box, then choose one component to test.')
                elif kind=='status':
                    if any(value[1:]):
                        self.stop();self.status.set('An output was still active; stop requested.')
                    else:
                        self.busy=False
                        self.status.set('All signals off. Observe the component to confirm it moved.')
                elif kind=='accepted':
                    self.status.set('Command accepted. Waiting for automatic release...')
                    self.root.after(750 if value=='servo' else 450,lambda:self.link.submit('status'))
                elif kind=='closed':
                    self.root.destroy();return
                elif kind=='error':
                    self.connected=False;self.busy=False
                    self.connection.set('Disconnected')
                    self.status.set(value)
                self.refresh()
        except queue.Empty:pass
        self.root.after(80,self.poll)

    def close(self):
        if self.closed:return
        self.closed=True;self.armed.set(False);self.busy=True;self.refresh()
        self.status.set('Stopping outputs and closing...')
        self.link.submit('close',priority=0)

def main():
    root=tk.Tk();ComponentTester(root);root.mainloop()

if __name__=='__main__':main()
