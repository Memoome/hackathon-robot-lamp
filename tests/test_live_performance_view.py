import sys,pathlib,time
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'apps/LJWB03-Lamp-Demo'))
import visual_control as v
import wireless_link
wireless_link.settings=lambda: {}
from lamp_demo import LampLink
root=v.tk.Tk();root.withdraw();app=v.App(root);app.auto_connect.set(False)
sent=[];app.link.submit=lambda *args:sent.append(args)
app.connected=True;app.state=dict(pulse=[0]*4,active=[0]*4,base_spin=0,moving=[0]*4)
rows=app.action_rows('Happy');cfg=app.run_config(rows,app.gesture_config(rows))
app.send('slump',(rows,cfg,10))
assert app.performance_active and app.monitor_heading.get()=='ROBOT PERFORMANCE · live commands'
assert str(app.monitor_run.cget('state'))=='disabled'
assert len(sent)==1
app.events.put(('run_phase',dict(index=2,total=8,name='Cheeky grin',pulse=[1100,1500,1300],base=1600)))
app.events.put(('state',dict(pulse=[1080,1510,1280,1580],active=[1]*4,base_spin=0,moving=[1]*4)))
app.events.put(('run_progress',36.5));app.events.put(('run_sound',(8,'accepted by board')))
app.poll()
assert app.pulse()==[1080,1510,1280] and app.base_target.get()==1580
assert app.playback_progress.get()==36.5 and 'Cheeky grin' in app.preview_phase.get()
assert 'accepted by board' in app.preview_cue.get()
app.events.put(('run_complete',None));app.events.put(('finished','Done. Last commanded pose is holding.'));app.poll()
assert not app.performance_active and app.playback_progress.get()==100 and app.preview_phase.get()=='Robot sequence complete'
app.performance_active=True;app.events.put(('error','Link lost'));app.poll()
assert not app.performance_active and 'cancelled' in app.preview_phase.get()
app.connected=True;app.performance_active=True;app.stop();assert not app.performance_active and sent[-1]==('stop',)
root.destroy()

# HTTP volume commands have no asynchronous completion reply. Poll status.
class SilentHTTP:
    def __init__(self):self.commands=[]
    def reset_input_buffer(self):pass
    def write(self,data):self.commands.append(data)
    def flush(self):pass
class Audio:
    def __init__(self):self.s=SilentHTTP();self.queries=[];self.count=0
    def check(self):pass
    def exchange(self,command,pattern):
        self.queries.append(command);self.count+=1
        if self.count<3:return b'STATUS mode=OFFLINE_PCM state=QUEUED busy=1 chip_ready=1 volume=15'
        return b'STATUS mode=OFFLINE_PCM state=READY busy=0 chip_ready=1 volume=90'
    def hold_pause(self,seconds):pass
audio=Audio();LampLink.set_speaker_volume(audio,90)
assert audio.s.commands==[b'audio_test volume 90\r\n'] and audio.queries==['audio_test status']*3
print('PASS: live monitor starts with Run, phase/arm/base/progress/sound events update, completion and disconnect/Stop differ, controls do not duplicate Run, HTTP volume confirmed through status without UART log.')
