"""Local-network transport. Pairing keys stay in LOCALAPPDATA, outside the project."""
import http.client,json,os,pathlib,socket,time
SETTINGS=pathlib.Path(os.environ.get('LOCALAPPDATA',str(pathlib.Path.home())))/'LJWB03'/'wireless.json'
def settings():
    try:return json.loads(SETTINGS.read_text(encoding='utf-8'))
    except FileNotFoundError:return {}
def save(data):
    SETTINGS.parent.mkdir(parents=True,exist_ok=True);tmp=SETTINGS.with_suffix('.tmp');tmp.write_text(json.dumps(data),encoding='utf-8');tmp.replace(SETTINGS)
def discover(device=None,timeout=.7):
    found={}
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);s.settimeout(.1)
        s.sendto(b'LAMP_DISCOVER_V1',('255.255.255.255',45832));until=time.monotonic()+timeout
        while time.monotonic()<until:
            try:
                raw,addr=s.recvfrom(200);tag,identity,port=raw.decode().split()
                if tag=='LAMP_V1' and (not device or identity==device) and port=='8032':found[identity]=addr[0]
            except socket.timeout:pass
            except (ValueError,UnicodeError):pass
    return found
def request(host,key,path,body,extra=None,timeout=1.2):
    c=http.client.HTTPConnection(host,8032,timeout=timeout)
    try:
        headers={'X-Lamp-Key':key,'Content-Type':'application/octet-stream'};headers.update(extra or {})
        c.request('POST',path,body,headers);r=c.getresponse();data=r.read()
        if r.status!=200:raise RuntimeError(f'Lamp Wi-Fi: {r.status} '+data.decode(errors='replace'))
        return data
    finally:c.close()
class HttpSerial:
    def __init__(self,host,key):self.host=host;self.key=key;self.pending=bytearray();self.input=bytearray();self.closed=False
    def reset_input_buffer(self):self.pending.clear()
    def write(self,data):
        if self.closed:raise RuntimeError('Wi-Fi connection closed')
        self.input.extend(data)
        while b'\n' in self.input:
            line,_,rest=self.input.partition(b'\n');self.input=bytearray(rest)
            if line.strip():self.pending.extend(request(self.host,self.key,'/command',line.strip()))
        return len(data)
    def read(self,n):
        if not self.pending:time.sleep(.01);return b''
        data=bytes(self.pending[:n]);del self.pending[:n];return data
    def flush(self):pass
    def close(self):self.closed=True
def open_connection(board_port,serial_module):
    cfg=settings()
    if cfg.get('enabled'):
        host=cfg.get('host');found=discover(cfg.get('device'))
        if found:host=next(iter(found.values()));cfg['host']=host;save(cfg)
        if not host:raise RuntimeError('Lamp not found. Check Wi-Fi or open Wireless setup.')
        return 'Wi-Fi '+host,HttpSerial(host,cfg['key'])
    p=board_port();s=serial_module.Serial(port=None,baudrate=115200,timeout=.025,rtscts=False,dsrdtr=False)
    s.dtr=False;s.rts=False;s.port=p;s.open();return p,s
