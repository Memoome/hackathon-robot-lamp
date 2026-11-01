"""Local-network transport. Pairing keys stay in LOCALAPPDATA, outside the project."""
import http.client,json,os,pathlib,socket,time,threading,queue,re
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
    """Race read-only USB and authenticated Wi-Fi probes; keep first valid lamp."""
    cfg=settings();results=queue.Queue();done=threading.Event();lock=threading.Lock()
    status=re.compile(rb'LIVE_STATUS version=1 session=\d+ gpio=12,10,11,15')
    def probe(factory):
        link=None
        try:
            label,link=factory()
            with lock:
                if done.is_set():link.close();return
                done.set();results.put((label,link,None));link=None
        except Exception as exc:results.put((None,None,str(exc)))
        finally:
            if link is not None:link.close()
    def usb():
        port=board_port();link=serial_module.Serial(port=None,baudrate=921600,timeout=.025,rtscts=False,dsrdtr=False)
        try:
            link.dtr=False;link.rts=False;link.port=port;link.open()
            link.reset_input_buffer();link.write(b'arm_live status\r\n');link.flush()
            raw=bytearray();until=time.monotonic()+1.5
            while time.monotonic()<until and not done.is_set():
                raw.extend(link.read(4096))
                if status.search(raw):return port,link
            raise RuntimeError('USB lamp did not reply')
        except Exception:link.close();raise
    def wifi(host):
        if not host:raise RuntimeError('No saved Wi-Fi address')
        raw=request(host,cfg['key'],'/command',b'arm_live status',timeout=.9)
        if not status.search(raw):raise RuntimeError('Wi-Fi device did not return lamp status')
        return 'Wi-Fi '+host,HttpSerial(host,cfg['key'])
    def discovered():
        found=discover(cfg.get('device'),timeout=.6)
        for host in found.values():
            if done.is_set():raise RuntimeError('Another connection won')
            try:return wifi(host)
            except Exception:continue
        raise RuntimeError('No paired lamp found on Wi-Fi')
    candidates=[usb]
    if cfg.get('key'):
        if cfg.get('host'):candidates.append(lambda:wifi(cfg['host']))
        candidates.append(discovered)
    for factory in candidates:threading.Thread(target=probe,args=(factory,),daemon=True).start()
    errors=[];until=time.monotonic()+3
    for _ in candidates:
        try:label,link,error=results.get(timeout=max(.01,until-time.monotonic()))
        except queue.Empty:break
        if link is not None:return label,link
        errors.append(error)
    done.set()
    raise RuntimeError('No lamp replied over USB or paired Wi-Fi. '+('; '.join(errors))[:300])
