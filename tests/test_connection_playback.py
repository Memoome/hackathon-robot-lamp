import sys,pathlib,time,threading,queue,types
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'apps/LJWB03-Lamp-Demo'))
import wireless_link as w
import visual_control as v
import wireless_link
wireless_link.settings=lambda: {}
STATUS=b'LIVE_STATUS version=1 session=42 gpio=12,10,11,15 pulse=0,0,0,0'
class Serial:
    instances=[]
    def __init__(self,**kw):self.closed=False;self.commands=[];self.instances.append(self)
    def open(self):pass
    def reset_input_buffer(self):pass
    def write(self,data):self.commands.append(data)
    def read(self,n):time.sleep(.01);return STATUS
    def flush(self):pass
    def close(self):self.closed=True
cfg=dict(enabled=False,host='example.invalid',key='test-key',device='test-device')
def missing():raise RuntimeError('USB absent')
for usb,delay,expected in ((lambda:'COM9',.12,'COM9'),(missing,0,'Wi-Fi example.invalid')):
    def reply(*args,**kwargs):time.sleep(delay);return STATUS
    with patch.object(w,'settings',return_value=cfg),patch.object(w,'discover',return_value={}),patch.object(w,'request',side_effect=reply):
        label,link=w.open_connection(usb,types.SimpleNamespace(Serial=Serial));assert label==expected
        time.sleep(.2);assert not getattr(link,'closed',False)
        link.close()
assert all(s.closed for s in Serial.instances)
assert all(cmd==b'arm_live status\r\n' for s in Serial.instances for cmd in s.commands)

# A rejected action must not turn into a connection failure.
from lamp_demo import LampLink
link=object.__new__(LampLink);link.jobs=queue.Queue();link.jobs.put(('slump',None));link.jobs.put(('close',None))
link.s=types.SimpleNamespace(close=lambda:None);link.state={};link.session=42;link.ui_alive=time.monotonic()
messages=[];stops=[];link.emit=lambda *args:messages.append(args);link.check=lambda:None
link.perform=lambda *args:(_ for _ in ()).throw(ValueError('Missing starting pose'))
link.stop_hardware=lambda release:stops.append((release,link.s is not None))
link.worker();assert not any(kind=='error' for kind,data in messages) and stops[0]==(False,True)

# Explicit Run prepares released joints; previews never submit this job.
class Device(v.VisualLink):
    def __init__(self):
        self.state=dict(active=[0]*4,pulse=[0]*4,base_spin=0);self.commands=[];self.emit=lambda *a:None
    def check(self):pass
    def exchange(self,cmd,*args):
        self.commands.append(cmd)
        if cmd.startswith('arm_live engage'):
            _,_,pin,pulse,hold=cmd.split();i=(12,10,11,15).index(int(pin));self.state['active'][i]=1;self.state['pulse'][i]=int(pulse)
    def expressive_glide(self,row,cfg):self.state['pulse'][:3]=row['pulse'].copy();self.state['pulse'][3]=row['base_pulse']
    def hold_pause(self,*args):pass
row=dict(name='test',pulse=[1000,1500,1500],seconds=1,pause=0,sound=-1,easing='quintic',delays=[0,0,0],base_pulse=1550)
cfg=dict(v.DEFAULT,run_engage=True,run_start=row['pulse'],run_base_start=1500)
d=Device();d.perform('slump',([row],cfg,10));assert d.state['active']==[1]*4 and d.state['pulse'][3]==1550
assert len([c for c in d.commands if c.startswith('arm_live engage')])==4
print('PASS: USB/Wi-Fi first valid connection wins, disabled old Wi-Fi toggle cannot block discovery, loser cleanup, read-only probes, rejected actions preserve connection, explicit Run engages released joints.')
