#include "lamp_led.h"
#include "peripheral/bsp_ws2812.h"
#include "qm_cli.h"
#include "wireless.h"
#undef QM_LOGI
#undef QM_LOGW
#undef QM_LOGE
#define QM_LOGI(tag,...) lamp_reply(__VA_ARGS__)
#define QM_LOGW(tag,...) lamp_reply(__VA_ARGS__)
#define QM_LOGE(tag,...) lamp_reply(__VA_ARGS__)
#define qm_cli_printf lamp_reply
#include "qm_log.h"
#include <stdlib.h>
#include <string.h>

#define TAG "lamp_led"
static int initialized;
static unsigned red,green,blue;
static void status(void) {
    QM_LOGI(TAG,"LED_STATUS version=1 gpio=%d leds=%d initialized=%d r=%u g=%u b=%u",
            BSP_WS2812_GPIO,BSP_WS2812_LED_NUM,initialized,red,green,blue);
}
static int component(const char *s,unsigned *value) {
    char *end;long n;
    if(!s || !*s)return 0;
    for(const char *p=s;*p;p++)if(*p<'0'||*p>'9')return 0;
    n=strtol(s,&end,10);if(*end || n<0 || n>255)return 0;
    *value=(unsigned)n;return 1;
}
static void command(char *out,int out_len,int argc,char **argv) {
    unsigned r=0,g=0,b=0;(void)out;(void)out_len;
    if(argc==2 && !strcmp(argv[1],"status")){status();return;}
    if(!((argc==2 && !strcmp(argv[1],"off")) ||
         (argc==5 && !strcmp(argv[1],"set") && component(argv[2],&r) && component(argv[3],&g) && component(argv[4],&b)))) {
        QM_LOGW(TAG,"LED_ERROR invalid_command use=lamp_led_set_R_G_B range=0..255");return;
    }
    if(!initialized) {
        if(bsp_ws2812_init()!=QM_EOK){QM_LOGE(TAG,"LED_ERROR init_failed");return;}
        initialized=1;
    }
    if(bsp_ws2812_fill((uint8_t)r,(uint8_t)g,(uint8_t)b)!=QM_EOK){QM_LOGE(TAG,"LED_ERROR write_failed");return;}
    red=r;green=g;blue=b;status();
}
static const struct qm_cli_command cli={"lamp_led","8-LED ring GPIO1: set R G B, off, status",command};
qm_err_t lamp_led_cli_init(void) {
    /* Registration only: no GPIO allocation, lights or automatic replay. */
    return qm_cli_register_command(&cli);
}

void lamp_remote_led(int argc,char **argv){command(NULL,0,argc,argv);}

qm_err_t lamp_led_boot_off(void) {
    qm_err_t rc=bsp_ws2812_init();
    if(rc!=QM_EOK)return rc;
    initialized=1;
    rc=bsp_ws2812_fill(0,0,0);
    if(rc==QM_EOK)red=green=blue=0;
    return rc;
}
