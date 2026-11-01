"""Local, explicit one-shot preview of the board's BF3901 camera."""
import os
import datetime,hashlib,json,os,pathlib,queue,re,struct,threading,time,zlib
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
import serial
from serial.tools import list_ports

HERE=pathlib.Path(__file__).resolve().parent
SERIAL=os.environ.get('LJWB03_SERIAL','')

def fnv32(data):
    h=2166136261
    for c in data:h=((h^c)*16777619)&0xffffffff
    return h

def decode_frame(raw):
    cleaned,removed=re.subn(rb'\[\d+\]<[A-Z]>[^\r\n]*\r+\n',b'',raw)
    begin=list(re.finditer(rb'CAM_BEGIN (\d+) (\d+) (\d+) (\S+) ([0-9a-fA-F]{8})',cleaned))
    end=list(re.finditer(rb'CAM_END (\d+) ([0-9a-fA-F]{8})',cleaned))
    if len(begin)!=1 or len(end)!=1:raise ValueError('The camera transfer did not finish. Try Capture again.')
    b,e=begin[0],end[0]
    size,w,h=int(b[1]),int(b[2]),int(b[3]);fmt=b[4].decode();checksum=int(b[5],16)
    if (size,w,h,fmt)!=(38400,120,160,'UYVY'):raise ValueError('Unexpected camera frame format.')
    if b.end()>=e.start() or int(e[1])!=size or int(e[2],16)!=checksum:raise ValueError('Camera transfer framing did not match.')
    data=bytearray()
    for m in re.finditer(rb'CAM_DATA (\d+) ([0-9a-fA-F]+)',cleaned[b.end():e.start()]):
        off=int(m[1]);part=bytes.fromhex(m[2].decode())
        if off!=len(data) or not 0<len(part)<=96 or len(data)+len(part)>size:raise ValueError('Missing or out-of-order image data.')
        data.extend(part)
    if len(data)!=size or fnv32(data)!=checksum:raise ValueError('The image checksum failed. No partial photo was accepted.')
    return bytes(data),{'bytes':size,'width':w,'height':h,'format':fmt,'fnv32':f'{checksum:08x}','sha256':hashlib.sha256(data).hexdigest(),'interleaved_log_records_removed':removed}

def uyvy_to_rgb(data):
    out=bytearray()
    def clip(x):return max(0,min(255,x))
    for i in range(0,len(data),4):
        u,y0,v,y1=data[i:i+4];d=u-128;e=v-128
        for y in (y0,y1):
            c=max(0,y-16)
            out.extend((clip((298*c+409*e+128)>>8),clip((298*c-100*d-208*e+128)>>8),clip((298*c+516*d+128)>>8)))
    return bytes(out)

def png_bytes(rgb,w,h):
    if len(rgb)!=w*h*3:raise ValueError('Invalid RGB image dimensions.')
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows=b''.join(b'\0'+rgb[y*w*3:(y+1)*w*3] for y in range(h))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')

def find_board():
    ports=[p.device for p in list_ports.comports() if (p.vid,p.pid)==(0x1a86,0x55d3) and (not SERIAL or p.serial_number==SERIAL)]
    if len(ports)!=1:raise RuntimeError('Board not found. Check its USB data cable, then click Connect.')
    return ports[0]

def open_board():
    p=find_board();s=serial.Serial(port=None,baudrate=921600,timeout=.12,rtscts=False,dsrdtr=False,xonxoff=False)
    s.dtr=False;s.rts=False;s.port=p;s.open();s.set_buffer_size(rx_size=65536,tx_size=8192)
    return s,p

def request(s,command,pattern,timeout,emit=lambda *x:None,cancel=None,transcript=None):
    s.reset_input_buffer();s.write((command+'\r\n').encode());s.flush()
    raw=bytearray();deadline=time.monotonic()+timeout;stop_sent=False
    while time.monotonic()<deadline:
        if cancel and cancel.is_set() and not stop_sent:
            s.write(b'cam_test stop\r\n');s.flush();stop_sent=True
        chunk=s.read(8192)
        if chunk:
            raw.extend(chunk)
            if transcript is not None:transcript.extend(chunk)
            error=re.search(rb'CAM_ERROR[^\r\n]*',raw)
            if error:
                text=error.group().decode(errors='replace')
                raise RuntimeError(text+'\nCheck 3.3V, ground, SDA21, SCL47, VSYNC4, PCLK9, D0→8, PWDN41.')
            if b'CAM_ABORT' in raw:raise RuntimeError('Capture cancelled. The previous picture is unchanged.')
            lines=list(re.finditer(rb'CAM_DATA (\d+) ([0-9a-fA-F]+)\r*\n',raw[-16384:]))
            if lines:
                last=lines[-1];n=min(38400,int(last[1])+len(last[2])//2)
                emit('progress',(f'Downloading photo... {n/384:.0f}%',n/384))
            elif b'CAM_CAPTURING' in raw:emit('progress',('Capturing a real frame from the board...',0))
            if re.search(pattern,raw):return bytes(raw)
    raise TimeoutError('No complete camera reply. Check wiring and close other serial test windows, then reconnect.')

def connect_and_probe():
    s,p=open_board()
    transcript=bytearray()
    try:
        with s:
            status=request(s,'cam_test status',rb'CAM_STATUS[^\r\n]*error=-?\d+',5,transcript=transcript)
            if b'pclk=9' not in status:raise RuntimeError('The camera firmware pin mapping does not match GPIO9.')
            request(s,'cam_test probe',rb'CAM_DONE result=OK',15,transcript=transcript)
    finally:(HERE/'connection.log').write_bytes(transcript)
    return p

def capture(emit=lambda *x:None,cancel=None):
    folder=HERE/'captures'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');folder.mkdir(parents=True)
    raw=bytearray()
    try:
        s,p=open_board()
        with s:
            transfer=request(s,'cam_test capture',rb'CAM_END \d+ [0-9a-fA-F]{8}',60,emit,cancel,raw)
        data,info=decode_frame(transfer)
        rgb=uyvy_to_rgb(data);png=png_bytes(rgb,info['width'],info['height'])
        (folder/'camera.uyvy').write_bytes(data);(folder/'photo.png').write_bytes(png)
        info.update({'port':p,'usb_serial':SERIAL,'sensor_frame':'240x320; downsampled 2x for USB preview','captured_at':datetime.datetime.now().isoformat(),'camera_clock_gpio':9,'original_camera_data_saved':True})
        (folder/'capture.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
        return {'folder':folder,'info':info,'rgb':rgb,'png':png}
    except Exception as exc:
        (folder/'error.txt').write_text(str(exc),encoding='utf-8');raise
    finally:(folder/'transfer.log').write_bytes(raw)

class CameraTester:
    def __init__(self,root):
        self.root=root;self.events=queue.Queue();self.busy=False;self.connected=False;self.result=None;self.photo=None;self.cancel=threading.Event()
        root.title('LJWB03 Camera Test');root.geometry('680x760');root.minsize(620,700)
        root.configure(bg='#f4f6f8');root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam');style.configure('TFrame',background='#f4f6f8')
        style.configure('TLabel',background='#f4f6f8',foreground='#182b3a',font=('Segoe UI',10))
        style.configure('TButton',font=('Segoe UI',10),padding=(12,6))
        style.configure('TProgressbar',thickness=6)
        box=ttk.Frame(root,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='Test your camera',font=('Segoe UI',18,'bold')).pack(anchor='w')
        ttk.Label(box,text='Capture a photo from the board and view it on your laptop.',foreground='#566575').pack(anchor='w',pady=(4,12))
        row=ttk.Frame(box);row.pack(fill='x')
        self.connection=tk.StringVar(value='Checking board and camera...')
        ttk.Label(row,textvariable=self.connection).pack(side='left')
        self.connect_button=ttk.Button(row,text='Connect',command=self.connect);self.connect_button.pack(side='right')
        controls=ttk.Frame(box);controls.pack(fill='x',pady=12)
        self.capture_button=ttk.Button(controls,text='Capture photo',command=self.capture);self.capture_button.pack(side='left',fill='x',expand=True)
        self.cancel_button=ttk.Button(controls,text='Cancel',command=self.cancel.set,state='disabled');self.cancel_button.pack(side='left',padx=8)
        self.save_button=ttk.Button(controls,text='Save a copy...',command=self.save,state='disabled');self.save_button.pack(side='right')
        self.progress=ttk.Progressbar(box,maximum=100);self.progress.pack(fill='x')
        self.status=tk.StringVar(value='Camera detection runs first. No photo is taken automatically by this window.')
        ttk.Label(box,textvariable=self.status,wraplength=550).pack(anchor='w',pady=(8,8))
        self.canvas=tk.Canvas(box,bg='#e8edf1',height=290,highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda event:self.draw())
        self.detail=tk.StringVar(value='A verified image will appear here after Capture. USB transfer takes about 10 seconds.')
        ttk.Label(box,textvariable=self.detail,foreground='#566575',font=('Segoe UI',9),wraplength=550).pack(anchor='w',pady=(8,6))
        self.folder_button=ttk.Button(box,text='Open saved photos',command=self.open_folder,state='disabled');self.folder_button.pack(anchor='w')
        self.refresh();root.after(100,self.poll);root.after(250,self.connect)

    def refresh(self):
        self.connect_button.configure(state='disabled' if self.busy else 'normal')
        self.capture_button.configure(state='normal' if self.connected and not self.busy else 'disabled')
        self.cancel_button.configure(state='normal' if self.busy and self.connected else 'disabled')
        self.save_button.configure(state='normal' if self.result and not self.busy else 'disabled')

    def connect(self):
        if self.busy:return
        self.busy=True;self.connected=False;self.refresh();self.connection.set('Checking camera...')
        def work():
            try:self.events.put(('connected',connect_and_probe()))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def capture(self):
        if self.busy or not self.connected:return
        self.busy=True;self.cancel.clear();self.progress['value']=0;self.status.set('Starting one camera capture...');self.refresh()
        def work():
            try:self.events.put(('captured',capture(lambda *x:self.events.put(x),self.cancel)))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='connected':
                    self.busy=False;self.connected=True;self.connection.set(f'Camera detected · {value}');self.status.set('Ready. Point the camera at something and press Capture photo.')
                elif kind=='progress':self.status.set(value[0]);self.progress['value']=value[1]
                elif kind=='captured':
                    self.busy=False;self.result=value;self.progress['value']=100
                    self.status.set('Photo received and checksum verified. Saved automatically.')
                    self.detail.set('120 × 160 camera preview, enlarged for viewing. Original UYVY data and PNG saved locally.')
                    self.folder_button.configure(state='normal');self.draw()
                elif kind=='error':
                    self.busy=False;self.status.set(value);self.progress['value']=0
                    if not self.connected:self.connection.set('Camera not detected')
                self.refresh()
        except queue.Empty:pass
        self.root.after(80,self.poll)

    def draw(self):
        c=self.canvas;c.delete('all');w,h=max(100,c.winfo_width()),max(100,c.winfo_height())
        if not self.result:c.create_text(w/2,h/2,text='Your camera photo will appear here',fill='#566575',font=('Segoe UI',13));return
        info=self.result['info'];ppm=f'P6\n{info["width"]} {info["height"]}\n255\n'.encode()+self.result['rgb']
        base=tk.PhotoImage(data=ppm,format='PPM')
        zoom=max(1,min((w-20)//info['width'],(h-20)//info['height']))
        self.photo=base.zoom(zoom,zoom);c.create_image(w/2,h/2,image=self.photo)

    def save(self):
        if not self.result:return
        path=filedialog.asksaveasfilename(parent=self.root,title='Save camera photo',defaultextension='.png',initialfile='camera-photo.png',filetypes=[('PNG image','*.png')])
        if path:pathlib.Path(path).write_bytes(self.result['png'])

    def open_folder(self):
        if self.result:os.startfile(str(self.result['folder']))

    def close(self):
        if self.busy:self.cancel.set();self.status.set('Cancelling... wait for the camera operation to finish, then close.');return
        self.root.destroy()

if __name__=='__main__':
    root=tk.Tk();CameraTester(root);root.mainloop()
