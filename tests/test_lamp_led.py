import pathlib,sys,tempfile,subprocess,json,copy,threading,time
root=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'apps/LJWB03-Lamp-Demo'))
import visual_control as v
import wireless_link
wireless_link.settings=lambda: {}
import lamp_demo as lamp
assert v.led_rgb('#FFD59A',10)==[26,21,15]
assert v.led_rgb('#FFFFFF',100)==[255]*3 and v.led_rgb('#FFFFFF',0)==[0]*3
for colour,level in [('#NOFFFF',10),('#FFFF',10),('#FFFFFF',101),('#FFFFFF',-1)]:
    try:v.led_rgb(colour,level);raise AssertionError('Invalid accepted')
    except ValueError:pass
class Fake:
    def __init__(self):self.calls=[];self.messages=[]
    def exchange(self,cmd,pattern):self.calls.append(cmd);return b'LED_STATUS version=1 gpio=1 leds=8 initialized=1 r=26 g=21 b=15\r\n'
    def emit(self,*msg):self.messages.append(msg)
f=Fake();lamp.LampLink.led(f,[26,21,15]);lamp.LampLink.led(f,None)
assert f.calls==['lamp_led set 26 21 15','lamp_led off']
for invalid in ([256,0,0],[-1,0,0],[0.5,0,0],[0,0]):
    try:lamp.LampLink.led(f,invalid);raise AssertionError()
    except ValueError:pass
before=(v.PROFILES/'final draft.json').read_bytes()
tkroot=v.tk.Tk();tkroot.withdraw();app=v.App(tkroot);app.auto_connect.set(False)
assert app.led_brightness.get()==10 and app.link.jobs.empty()
app.connected=True;app.led_power.set(True);app.apply_led();kind,payload=app.link.jobs.get_nowait()
assert kind=='led' and payload==[26,21,15]
app.busy=False;app.apply_led(off=True);assert app.link.jobs.get_nowait()==('led',None)
assert app.link.s is None and (v.PROFILES/'final draft.json').read_bytes()==before
app.link.closing=True;tkroot.destroy()

source=(root/'firmware/overlay/apps/main/lamp_led.c').read_text()
body='\n'.join(line for line in source.splitlines() if not line.startswith('#include'))
stub=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <assert.h>
typedef int qm_err_t;
#define QM_EOK 0
#define BSP_WS2812_GPIO 1
#define BSP_WS2812_LED_NUM 8
static char logline[512];static int init_calls,fill_calls,fail_init,fail_fill;static unsigned rgb[3];
static int lamp_reply(const char *fmt,...){va_list ap;va_start(ap,fmt);vsnprintf(logline,sizeof(logline),fmt,ap);va_end(ap);return 0;}
static void logmsg(const char *tag,const char *fmt,...){va_list ap;va_start(ap,fmt);vsnprintf(logline,sizeof(logline),fmt,ap);va_end(ap);}
#define QM_LOGI logmsg
#define QM_LOGW logmsg
#define QM_LOGE logmsg
static int bsp_ws2812_init(void){init_calls++;return fail_init?-1:0;}
static int bsp_ws2812_fill(uint8_t r,uint8_t g,uint8_t b){fill_calls++;rgb[0]=r;rgb[1]=g;rgb[2]=b;return fail_fill?-1:0;}
struct qm_cli_command {const char *name,*help;void(*fn)(char*,int,int,char**);};
static int qm_cli_register_command(const struct qm_cli_command*c){assert(!strcmp(c->name,"lamp_led"));return 0;}
'''
test=r'''
static void cmd(const char *text){char buf[256];strcpy(buf,text);char *argv[8];int n=0;for(char*p=strtok(buf," ");p;p=strtok(NULL," ")){assert(n<8);argv[n++]=p;}command(NULL,0,n,argv);}
int main(void){
 assert(!lamp_led_cli_init()&&!init_calls&&!fill_calls);
 cmd("lamp_led status");assert(strstr(logline,"gpio=1 leds=8 initialized=0")&&!init_calls);
 const char*bad[]={"lamp_led set 256 0 0","lamp_led set -1 0 0","lamp_led set 1.2 0 0","lamp_led set 255 0","lamp_led set 1 2 3 4","lamp_led set 9999999999999999999999999 0 0"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++){cmd(bad[i]);assert(strstr(logline,"LED_ERROR")&&!init_calls&&!fill_calls);}
 fail_init=1;cmd("lamp_led off");assert(!initialized&&strstr(logline,"init_failed"));fail_init=0;
 cmd("lamp_led set 26 21 15");assert(initialized&&rgb[0]==26&&rgb[1]==21&&rgb[2]==15);
 unsigned previous=red;fail_fill=1;cmd("lamp_led set 255 255 255");assert(red==previous&&strstr(logline,"write_failed"));fail_fill=0;
 cmd("lamp_led off");assert(!red&&!green&&!blue&&!rgb[0]&&!rgb[1]&&!rgb[2]);
 puts("PASS: actual firmware CLI bounds, no output on register/status/invalid input, driver errors and exact set/off.");
}
'''
with tempfile.TemporaryDirectory(dir=root/'tests') as tmp:
    c=pathlib.Path(tmp)/'test.c';exe=pathlib.Path(tmp)/'test.exe';c.write_text(stub+body+test)
    subprocess.run(['gcc',str(c),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
print('PASS: brightness scaling, independent LED-only commands, idle GUI, Off, and locked calibration preserved.')
