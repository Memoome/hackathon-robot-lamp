"""Exercise the Wi-Fi transport without a board, credentials or network access."""
import sys,pathlib,tempfile,json
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'apps/LJWB03-Lamp-Demo'))
import wireless_link as w

calls=[]
def reply(host,key,path,body,**kwargs):
    calls.append((host,key,path,body))
    return b'LIVE_STATUS example\n'
with patch.object(w,'request',side_effect=reply):
    link=w.HttpSerial('example.invalid','test-key')
    link.write(b'arm_live sta');assert not calls
    link.write(b'tus\n');assert calls[-1][3]==b'arm_live status'
    assert link.read(5)+link.read(100)==b'LIVE_STATUS example\n'
    link.close()
    try:link.write(b'arm_live status\n');raise AssertionError('Closed link accepted data')
    except RuntimeError:pass

cfg=dict(enabled=True,host='old.invalid',device='example-device',key='test-key')
with patch.object(w,'settings',return_value=cfg),patch.object(w,'discover',return_value={'example-device':'new.invalid'}),patch.object(w,'save') as save:
    label,link=w.open_connection(lambda: (_ for _ in ()).throw(AssertionError('USB used')),None)
    assert label=='Wi-Fi new.invalid' and link.host=='new.invalid'
    assert save.call_args.args[0]['host']=='new.invalid'
    assert not link.input and not link.pending

class Response:
    status=403
    def read(self):return b'Pairing key required'
class Connection:
    def __init__(self,*args,**kwargs):self.closed=False;self.sent=None
    def request(self,*args):self.sent=args
    def getresponse(self):return Response()
    def close(self):self.closed=True
connection=Connection()
with patch.object(w.http.client,'HTTPConnection',return_value=connection):
    try:w.request('example.invalid','test-key','/command',b'arm_live status');raise AssertionError('403 accepted')
    except RuntimeError as exc:assert '403' in str(exc) and 'test-key' not in str(exc)
    assert connection.closed and connection.sent[3]['X-Lamp-Key']=='test-key'

with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent) as directory,patch.object(w,'SETTINGS',pathlib.Path(directory)/'wireless.json'):
    assert w.settings()=={}
    w.save(cfg);assert w.settings()==cfg
print('PASS: Wi-Fi framing, closed-link rejection, discovery address refresh, no USB fallback/auto-command, authentication failure and private settings roundtrip.')
