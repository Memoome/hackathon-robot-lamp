"""Local setup window. Secrets are sent over USB, never written to PC logs."""
import sys,pathlib,threading,queue,time,re,subprocess,tkinter as tk
from tkinter import ttk,messagebox
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'LJWB03-Arm-Controller'))
from arm_controller import board_port
import serial

def hex_field(value,limit,empty=False):
    raw=value.encode('utf-8')
    if b'\0' in raw or len(raw)>limit or (not empty and not raw):raise ValueError(f'Field must contain 1–{limit} UTF-8 bytes.')
    return raw.hex() or '-'

def parse_status(raw):
    m=re.search(rb'NET_STATUS version=1 wifi=(\d) ip=([\d.]+) rssi=(-?\d+) cloud=(\d) cloud_started=(\d) product=(\d+) identity=(\d) rc=(-?\d+)',raw)
    if not m:raise RuntimeError('Connection-setup firmware not detected. Install the prepared update first.')
    v=[x.decode() for x in m.groups()]
    return dict(zip(('wifi','ip','rssi','cloud','started','product','identity','rc'),v))

def wifi_command(ssid,password,open_network=False):
    if not ssid:raise ValueError('Enter the Wi-Fi network name, or use the PC hotspot button.')
    if open_network:
        password=''
    else:
        n=len(password.encode('utf-8'))
        if n<8:raise ValueError('Enter the Windows hotspot Wi-Fi password (at least 8 characters), not your LJYD product secret. You can use “Use this PC hotspot” to avoid typing it. Select “Network has no password” only for an open network.')
        if n>64 or (n==64 and not re.fullmatch(r'[0-9a-fA-F]{64}',password)):
            raise ValueError('Use an 8–63 byte Wi-Fi passphrase, or a 64-digit hexadecimal Wi-Fi key.')
    return 'net_setup wifi '+hex_field(ssid,32)+' '+hex_field(password,64,True)

class App:
    def __init__(self,root):
        self.root=root;root.title('Robot · Wi-Fi and LJYD setup');root.geometry('730x830');root.minsize(690,790)
        self.events=queue.Queue();self.jobs=queue.Queue();self.connected=False;self.usb='';self.last_refresh=0
        f=ttk.Frame(root,padding=22);f.pack(fill='both',expand=True)
        ttk.Label(f,text='Connect your robot',font=('Segoe UI',19,'bold')).pack(anchor='w')
        ttk.Label(f,text='Wi-Fi first, then your team’s LJYD project.',padding=(0,5)).pack(anchor='w')
        row=ttk.Frame(f);row.pack(fill='x',pady=10)
        ttk.Button(row,text='Connect board by USB',command=lambda:self.jobs.put(('connect',None))).pack(side='left')
        ttk.Button(row,text='Refresh status',command=lambda:self.send('net_setup status')).pack(side='left',padx=8)
        self.state=tk.StringVar(value='Disconnected. Close the arm/demo window before connecting here.')
        ttk.Label(f,textvariable=self.state,wraplength=620).pack(anchor='w',pady=8)
        self.note=tk.StringVar(value='Ready when you are.')
        ttk.Label(f,textvariable=self.note,wraplength=620,foreground='#195a79').pack(anchor='w')
        net=ttk.LabelFrame(f,text='1 · Wi-Fi (2.4 GHz)',padding=12);net.pack(fill='x',pady=8)
        self.ssid=tk.StringVar();self.password=tk.StringVar()
        self.open_network=tk.BooleanVar(value=False);self.show_wifi_password=tk.BooleanVar(value=False)
        saved=pathlib.Path(__file__).with_name('pc-hotspot-connection.json')
        if saved.exists():
            try:
                import json
                self.ssid.set(json.loads(saved.read_text()).get('ssid',''))
            except (ValueError,OSError):pass
        self.field(net,'Network name',self.ssid,0);self.wifi_entry=self.field(net,'Wi-Fi password',self.password,1,True)
        options=ttk.Frame(net);options.grid(row=2,column=0,columnspan=2,sticky='w')
        ttk.Checkbutton(options,text='Show password',variable=self.show_wifi_password,command=lambda:self.wifi_entry.configure(show='' if self.show_wifi_password.get() else '●')).pack(side='left')
        ttk.Checkbutton(options,text='Network has no password',variable=self.open_network,command=lambda:self.wifi_entry.configure(state='disabled' if self.open_network.get() else 'normal')).pack(side='left',padx=12)
        ttk.Button(net,text='Save Wi-Fi and connect',command=self.wifi).grid(row=3,column=1,sticky='w',pady=6)
        ttk.Button(net,text='Use this PC hotspot (no password typing)',command=self.pc_hotspot).grid(row=4,column=1,sticky='w',pady=4)
        ttk.Label(net,text='This is the Wi-Fi password shown in Windows Mobile hotspot settings.\nThe LJYD product secret belongs in the separate section below.',wraplength=600).grid(row=5,column=0,columnspan=2,sticky='w',pady=3)
        cloud=ttk.LabelFrame(f,text='2 · LJYD project',padding=12);cloud.pack(fill='x',pady=8)
        self.pid=tk.StringVar();self.secret=tk.StringVar()
        self.field(cloud,'Product ID',self.pid,0);self.field(cloud,'Product secret',self.secret,1,True)
        ttk.Label(cloud,text='Use your team’s product details from LJYD. Ask Percy if needed.',wraplength=570).grid(row=2,column=0,columnspan=2,sticky='w',pady=4)
        ttk.Button(cloud,text='Save team identity',command=self.identity).grid(row=3,column=1,sticky='w',pady=4)
        ttk.Button(cloud,text='Connect to LJYD',command=lambda:self.send('net_setup cloud')).grid(row=4,column=1,sticky='w',pady=4)
        ttk.Label(f,text='Passwords are hidden and are not saved in PC logs. Settings are stored on the board.\nWi-Fi reconnects after restart; press Connect to LJYD again after a restart.\nThis window does not move the arm, record audio, or upload camera images.',wraplength=620).pack(anchor='w',pady=10)
        root.protocol('WM_DELETE_WINDOW',lambda:self.jobs.put(('close',None)))
        threading.Thread(target=self.worker,daemon=True).start();root.after(100,self.poll)
    def field(self,f,label,var,row,secret=False):
        ttk.Label(f,text=label).grid(row=row,column=0,sticky='w',padx=(0,15),pady=4)
        entry=ttk.Entry(f,textvariable=var,show='●' if secret else '',width=42);entry.grid(row=row,column=1,sticky='ew',pady=4);f.columnconfigure(1,weight=1);return entry
    def send(self,command):
        if not self.connected:messagebox.showinfo('Connect first','Connect the board by USB first.');return False
        self.note.set('Working…');self.jobs.put(('command',command));return True
    def wifi(self):
        try:
            if not self.connected:messagebox.showinfo('Connect first','Connect the board by USB first.');return
            self.send(wifi_command(self.ssid.get(),self.password.get(),self.open_network.get()))
        except ValueError as e:messagebox.showerror('Check Wi-Fi details',str(e))
    def pc_hotspot(self):
        self.note.set('Using Windows hotspot settings. This may take up to 90 seconds…')
        self.jobs.put(('pc_hotspot',None))
    def identity(self):
        try:
            p=int(self.pid.get())
            if not 1<=p<=4294967295:raise ValueError('Enter a valid numeric Product ID.')
            self.send(f'net_setup identity {p} '+hex_field(self.secret.get(),64))
        except ValueError as e:messagebox.showerror('Check product details',str(e))
    def worker(self):
        s=None
        def exchange(cmd):
            s.reset_input_buffer();s.write((cmd+'\r\n').encode());raw=b'';end=time.monotonic()+6
            while time.monotonic()<end:
                raw+=s.read(4096)
                if b'NET_ERROR' in raw:raise RuntimeError('Request rejected. Wi-Fi must be online and team identity saved before cloud connection. Restart before changing an already-started cloud identity.')
                if b'NET_STATUS version=1' in raw and b'\n' in raw[raw.index(b'NET_STATUS version=1'):]:return parse_status(raw)
            raise RuntimeError('No setup reply. Check USB and close other controller windows.')
        while True:
            kind,data=self.jobs.get()
            try:
                if kind=='close':
                    if s:s.close()
                    self.events.put(('close',None));return
                if kind=='connect':
                    if s:s.close()
                    port=board_port();s=serial.Serial(port=None,baudrate=115200,timeout=.1);s.dtr=False;s.rts=False;s.port=port;s.open()
                    s.write(b'arm_live status\r\n');raw=b'';until=time.monotonic()+3
                    while time.monotonic()<until:
                        raw+=s.read(4096)
                        if re.search(rb'LIVE_STATUS[^\r\n]+lease=\d',raw):break
                    if not re.search(rb'active=0,0,0,0 moving=0,0,0,0 base_spin=0',raw):
                        s.close();s=None;raise RuntimeError('Support the arm, release all outputs in the earlier controller, and close it before setup.')
                    state=exchange('net_setup status')
                    self.events.put(('connected',port));self.events.put(('status',state))
                elif kind=='command':
                    if not s:raise RuntimeError('Connect the board first.')
                    self.events.put(('status',exchange(data)))
                    data=None
                elif kind=='pc_hotspot':
                    if s:s.close();s=None
                    self.events.put(('disconnected',None))
                    raise RuntimeError('Configure a 2.4GHz hotspot in Windows Settings, then enter its SSID/password in this window.')
                    script=pathlib.Path('unused')
                    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Mode','Configure'],capture_output=True,text=True,timeout=150,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if result.returncode:raise RuntimeError('PC hotspot connection failed. Check Windows Mobile hotspot is sharing school Wi-Fi on 2.4 GHz, and USB is attached. '+result.stderr[-900:])
                    import json
                    saved=json.loads(pathlib.Path(__file__).with_name('pc-hotspot-connection.json').read_text())
                    self.events.put(('hotspot_saved',saved['ssid']));self.jobs.put(('connect',None))
            except Exception as e:
                if kind=='connect' or isinstance(e,serial.SerialException):
                    if s:s.close();s=None
                    self.events.put(('disconnected',None))
                self.events.put(('error',str(e)))
    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='close':self.root.destroy();return
                if kind=='connected':self.connected=True;self.usb=data
                elif kind=='disconnected':self.connected=False;self.state.set('USB disconnected. Reconnect the board when ready.')
                elif kind=='hotspot_saved':self.ssid.set(data);self.password.set('');self.open_network.set(False);self.wifi_entry.configure(state='normal')
                elif kind=='error':self.note.set(data)
                elif kind=='status':
                    wifi='Online' if data['wifi']=='1' else 'Not connected'
                    cloud='Online' if data['cloud']=='1' else ('NOT ONLINE — registration requested' if data['started']=='1' else 'Not started')
                    self.state.set(f"USB: Connected ({self.usb})\nBoard Wi-Fi: {wifi} · IP: {data['ip']} · Signal: {data['rssi']} dBm\nLJYD: {cloud} · Team product: {data['product'] if data['identity']=='1' else 'Not set'}")
                    self.note.set(('Board has joined Wi-Fi. LJYD registration is a separate step.' if data['wifi']=='1' else 'Board is not on Wi-Fi yet. Check hotspot settings; status updates automatically.') if data['rc']=='0' else 'Connection error '+data['rc'])
                    if data['wifi']=='1' and data['started']=='1' and data['cloud']!='1':self.note.set('Wi-Fi works and the product is saved, but cloud login is NOT confirmed. A registration attempt may have failed; this is not a success indicator.')
                    try:
                        import json,datetime
                        report=dict(data,checked_at=datetime.datetime.now().isoformat())
                        pathlib.Path(__file__).with_name('connection-status.json').write_text(json.dumps(report,indent=2))
                    except OSError:pass
        except queue.Empty:pass
        if self.connected and time.monotonic()-self.last_refresh>3 and self.jobs.empty():
            self.last_refresh=time.monotonic();self.jobs.put(('command','net_setup status'))
        self.root.after(100,self.poll)

if __name__=='__main__':
    app=App(tk.Tk())
    if '--connect' in sys.argv:app.jobs.put(('connect',None))
    app.root.mainloop()
