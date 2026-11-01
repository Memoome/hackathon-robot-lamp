"""Host fault tests for the actual boot target function; no hardware access."""
import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FW = ROOT / 'firmware/overlay/apps/main'

class BootRestTests(unittest.TestCase):
    def test_generated_target_matches_package(self):
        spec = importlib.util.spec_from_file_location('export_boot_rest', ROOT / 'tools/export_boot_rest.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.assertEqual((FW / 'boot_rest_target.h').read_text(), module.render())

    def test_actual_startup_and_pwm_failures(self):
        source = (FW / 'actuator_test.c').read_text()
        function = source[source.index('esp_err_t lamp_boot_return_rest(void)'):source.index('static void live_freeze(')]
        stub = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "boot_rest_target.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_STATE 1
#define portMAX_DELAY 0
#define QM_LOGI(...) ((void)0)
#define QM_LOGE(...) ((void)0)
static int ready,lock,boot_rest_attempted,updating,boot_rest_owned,base_spinning,calls,fail_at,held;
static int64_t deadlines[4],live_motion_until[4],live_fraction[4],base_stop_until,arm_lease;
static int live_dir[4],live_hold[4];
static unsigned pulses[4];
static void xSemaphoreTake(int l,int t){(void)l;(void)t;assert(!held);held=1;}
static void xSemaphoreGive(int l){(void)l;assert(held);held=0;}
static int live_write(int i,unsigned p){assert(held);calls++;if(i==fail_at)return -7;pulses[i]=p;return 0;}
static void release_all_locked(void){memset(deadlines,0,sizeof deadlines);memset(pulses,0,sizeof pulses);boot_rest_owned=0;arm_lease=0;}
static void reset(void){ready=1;boot_rest_attempted=updating=boot_rest_owned=calls=held=0;fail_at=-1;release_all_locked();}
'''
        tests = r'''
int main(void){
 reset();ready=0;assert(lamp_boot_return_rest()==ESP_ERR_INVALID_STATE && calls==0);
 reset();updating=1;assert(lamp_boot_return_rest()==ESP_ERR_INVALID_STATE && calls==0 && !held);
 reset();deadlines[2]=-1;assert(lamp_boot_return_rest()==ESP_ERR_INVALID_STATE && calls==0 && !held);
 reset();assert(lamp_boot_return_rest()==0 && calls==4 && boot_rest_owned && !arm_lease && !held);
 for(int i=0;i<4;i++){assert(pulses[i]==lamp_boot_rest_pulse[i]);assert(deadlines[i]==-1 && live_hold[i]);}
 assert(lamp_boot_return_rest()==ESP_ERR_INVALID_STATE && calls==4);
 release_all_locked();assert(lamp_boot_return_rest()==ESP_ERR_INVALID_STATE && calls==4);
 for(int fail=0;fail<4;fail++){
  reset();fail_at=fail;assert(lamp_boot_return_rest()==-7 && !held && !boot_rest_owned);
  for(int i=0;i<4;i++)assert(!deadlines[i] && !pulses[i]);
  assert(lamp_boot_return_rest()==ESP_ERR_INVALID_STATE);
 }
 puts("startup, one-shot, active-output guard, update guard, four PWM failures PASS");
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp); (path/'test.c').write_text(stub+function+tests)
            subprocess.run(['cc','-std=c99','-Wall','-Werror','-I',str(FW),str(path/'test.c'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)

if __name__ == '__main__': unittest.main()
