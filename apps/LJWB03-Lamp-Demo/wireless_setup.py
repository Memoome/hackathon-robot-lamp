"""USB provisioning, local pairing and deliberate Wi-Fi firmware updates."""
import hashlib,json,pathlib,queue,re,secrets,sys,threading,time,tkinter as tk
from tkinter import ttk,messagebox,filedialog
import wireless_link as w
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'LJWB03-Arm-Controller'))
from arm_controller import board_port
import serial
def usb_query(s,command,seconds=1):
    s.reset_input_buffer();s.write((command+'\r\n').encode());s.flush();raw=bytearray();end=time.monotonic()+seconds
    while time.monotonic()<end:raw.extend(s.read(4096))
    return bytes(raw)
def usb_open():
    s=serial.Serial(port=None,baudrate=921600,timeout=.03);s.dtr=False;s.rts=False;s.port=board_port();s.open();return s
class Setup:
 def __init__(self,root):
    self.root=root;root.title('Lamp wireless setup');root.geometry('620x470');self.q=queue.Queue();self.cfg=w.settings()
    box=ttk.Frame(root,padding=18);box.pack(fill='both',expand=True)
    ttk.Label(box,text='Lamp Wi-Fi & updates',font=('Segoe UI',19,'bold')).pack(anchor='w')
    ttk.Label(box,text='Disconnect Studio before USB setup. Support the lamp and turn servo power off.\nSaved pairing details stay privately on this PC.',wraplength=580).pack(anchor='w',pady=10)
    self.ssid=tk.StringVar();self.password=tk.StringVar();self.host=tk.StringVar(value=self.cfg.get('host',''))
    for title,var,secret in [('2.4GHz network',self.ssid,False),('Wi-Fi password',self.password,True),('Board IP (optional)',self.host,False)]:
        row=ttk.Frame(box);row.pack(fill='x',pady=4);ttk.Label(row,text=title,width=20).pack(side='left');ttk.Entry(row,textvariable=var,show='•' if secret else '').pack(side='left',fill='x',expand=True)
    self.buttons=[]
    for label,fn in [('1. Save Wi-Fi via USB',self.wifi),('2. Pair this PC via USB',self.pair),('3. Find lamp & enable wireless',self.enable),('Use USB instead',self.usb),('Upload firmware over Wi-Fi…',self.update)]:
        b=ttk.Button(box,text=label,command=lambda f=fn:self.start(f));b.pack(fill='x',pady=3);self.buttons.append(b)
    self.status=tk.StringVar(value='Wireless mode: '+('enabled' if self.cfg.get('enabled') else 'off'))
    ttk.Label(box,textvariable=self.status,wraplength=575).pack(anchor='w',pady=10);root.after(100,self.poll)
 def start(self,fn):
    # Read Tk values and show confirmations only on the UI thread.
    self.values=(self.ssid.get(),self.password.get(),self.host.get().strip())
    if fn==self.update:
        path=filedialog.askopenfilename(title='Select compiled ESP32-S3 application (.bin)',filetypes=[('Firmware','*.bin')])
        if not path:return
        if not messagebox.askokcancel('Restart lamp','Support the lamp, Release all and switch servo power off. Close Studio. Uploading firmware restarts the board. Continue?'):return
        self.image=path
    for b in self.buttons:b.configure(state='disabled')
    self.status.set('Working…')
    def run():
        try:self.q.put((True,fn()))
        except Exception as e:self.q.put((False,str(e)))
    threading.Thread(target=run,daemon=True).start()
 def poll(self):
    try:
        ok,text=self.q.get_nowait();self.status.set(text)
        for b in self.buttons:b.configure(state='normal')
        if ok:self.password.set('')
    except queue.Empty:pass
    self.root.after(100,self.poll)
 def wifi(self):
    ssid,password,_=self.values
    if not 1<=len(ssid.encode())<=32 or not 8<=len(password.encode())<=63:raise ValueError('Enter a network name and password of 8–63 bytes.')
    with usb_open() as s:
        state=usb_query(s,'arm_live status')
        if b'active=0,0,0,0' not in state:raise RuntimeError('Release all in Studio, then disconnect Studio first.')
        raw=usb_query(s,'net_setup wifi '+ssid.encode().hex()+' '+password.encode().hex(),2)
        if b'NET_RESULT rc=0' not in raw:raise RuntimeError('Board did not accept Wi-Fi settings.')
        end=time.monotonic()+45
        while time.monotonic()<end:
            raw=usb_query(s,'net_setup status');m=re.search(rb'wifi=1 ip=([0-9.]+)',raw)
            if m:self.cfg['host']=m[1].decode();w.save(self.cfg);return 'Wi-Fi connected at '+self.cfg['host']+'. Now pair this PC.'
    raise RuntimeError('Settings saved, but Wi-Fi has not connected. Check network/password and 2.4GHz availability.')
 def pair(self):
    key=secrets.token_hex(32)
    with usb_open() as s:
        raw=usb_query(s,'lamp_wireless pair '+key)
        if b'WIRELESS_PAIR rc=0' not in raw:raise RuntimeError('Wireless firmware not detected, or USB busy.')
        raw=usb_query(s,'net_setup status');m=re.search(rb'wifi=1 ip=([0-9.]+)',raw)
        if m:self.cfg['host']=m[1].decode()
    self.cfg['key']=key;self.cfg['enabled']=False;w.save(self.cfg);return 'Paired. Click Find lamp & enable wireless.'
 def enable(self):
    if not self.cfg.get('key'):raise RuntimeError('Pair this PC via USB first.')
    found=w.discover(timeout=1.5);host=self.values[2] or self.cfg.get('host')
    if self.cfg.get('device') in found:host=found[self.cfg['device']]
    elif len(found)==1:self.cfg['device'],host=next(iter(found.items()))
    if not host:raise RuntimeError('No lamp found. Enter its IP, or check that the Wi-Fi permits local devices to communicate.')
    raw=w.request(host,self.cfg['key'],'/command',b'arm_live status')
    if b'LIVE_STATUS' not in raw:raise RuntimeError('No valid lamp reply.')
    self.cfg.update(host=host,enabled=True);w.save(self.cfg)
    return 'Wireless enabled at '+host+'. Reopen Studio; USB data cable is now optional.'
 def usb(self):
    self.cfg['enabled']=False;w.save(self.cfg);return 'USB mode selected. Reconnect Studio.'
 def update(self):
    cfg=w.settings();host=self.values[2] or cfg.get('host')
    if not host or not cfg.get('key'):raise RuntimeError('Pair and connect the lamp first.')
    blob=pathlib.Path(self.image).read_bytes()
    if not 1024<=len(blob)<=0x3f0000 or blob[0]!=0xe9:raise ValueError('Select an ESP32 application image, not a ZIP or merged full-flash backup.')
    digest=hashlib.sha256(blob).hexdigest()
    result=w.request(host,cfg['key'],'/update',blob,{'X-Image-SHA256':digest},timeout=120)
    if b'UPDATE_OK' not in result:raise RuntimeError('No successful update acknowledgement.')
    return 'Firmware installed; board is restarting. Reconnect Studio after it joins Wi-Fi.'
if __name__=='__main__':
 root=tk.Tk();Setup(root);root.mainloop()
