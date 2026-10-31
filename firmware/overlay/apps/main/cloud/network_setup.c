#include "qm_config.h"
#if CONFIG_OFFLINE_AUDIO_TEST
#include "qm.h"
#include "qm_cli.h"
#include "qm_wifi.h"
#include "qm_kv.h"
#include "ljyd_cloud.h"
#include "network_setup.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include <string.h>
#include <stdlib.h>
#include <limits.h>

/* Separate namespace: never enroll with the sample product or old saved keys. */
static struct { uint32_t pid; char secret[65]; } identity;
static volatile int online, cloud_online;
static int wifi_started, cloud_initialized, enabled, last_rc;
static uint8_t wifi_enabled;
extern int qm_hal_wifi_init(void);
uint32_t network_product_id(void) { return identity.pid; }
const char *network_product_secret(void) { return identity.secret; }
static int unhex(const char *src, unsigned char *dst, int cap)
{
    size_t n=strlen(src);
    if (!strcmp(src,"-")) return 0;
    if ((n&1) || n>(size_t)cap*2) return -1;
    for(size_t i=0;i<n;i++) if(!((src[i]>='0'&&src[i]<='9')||(src[i]>='a'&&src[i]<='f')||(src[i]>='A'&&src[i]<='F'))) return -1;
    for(size_t i=0;i<n/2;i++){char b[3]={src[2*i],src[2*i+1],0};dst[i]=(unsigned char)strtoul(b,NULL,16);if(!dst[i])return -1;}
    return (int)n/2;
}
static void cloud_event(ljyd_cloud_event_t event,void *handle,void *data)
{ (void)handle;(void)data;cloud_online=(event==LJYD_CLOUD_EVENT_CONNECTED); }
static void wifi_event(void *arg,qm_event_base_t base,int32_t id,void *data,size_t size)
{
    (void)arg;(void)base;(void)data;(void)size;
    if(id==QM_WIFI_EVENT_STA_START) last_rc=qm_wifi_connect();
    if(id==QM_WIFI_EVENT_STA_GOT_IP){online=1;if(enabled)ljyd_cloud_on_network_up();}
    if(id==QM_WIFI_EVENT_STA_DISCONNECTED||id==QM_WIFI_EVENT_STA_LOST_IP||id==QM_WIFI_EVENT_STA_STOP){online=0;cloud_online=0;if(enabled)ljyd_cloud_on_network_down();}
}
static void status(void)
{
    esp_netif_ip_info_t ip={0};wifi_ap_record_t ap={0};
    esp_netif_t *net=esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if(net)esp_netif_get_ip_info(net,&ip);
    esp_wifi_sta_get_ap_info(&ap);
    qm_cli_printf("\r\nNET_STATUS version=1 wifi=%d ip=" IPSTR " rssi=%d cloud=%d cloud_started=%d product=%lu identity=%d rc=%d\r\n",online,IP2STR(&ip.ip),ap.rssi,cloud_online,enabled,(unsigned long)identity.pid,identity.pid&&identity.secret[0],last_rc);
}
static void command(char *out,int len,int argc,char **argv)
{
    (void)out;(void)len;
    if(argc==2&&!strcmp(argv[1],"status")){status();return;}
    if(argc==4&&!strcmp(argv[1],"wifi")){
        qm_wifi_config_t cfg={0};
        int sn=unhex(argv[2],cfg.sta.ssid,32),pw=unhex(argv[3],cfg.sta.password,64);
        if(sn<1||pw<0||(pw>0&&pw<8))goto invalid;
        cfg.sta.ssid_len=sn;cfg.sta.password_len=pw;
        if(wifi_started){last_rc=qm_wifi_stop();wifi_started=0;online=0;if(last_rc)goto done;}
        last_rc=qm_wifi_set_mode(QM_WIFI_MODE_STA);
        if(!last_rc)last_rc=qm_wifi_set_config(QM_WIFI_IF_STA,&cfg);
        memset(&cfg,0,sizeof(cfg));
        if(!last_rc){wifi_enabled=1;last_rc=qm_kv_set("armnet/wifi",&wifi_enabled,sizeof(wifi_enabled),1);}
        if(!last_rc){last_rc=qm_wifi_start();wifi_started=!last_rc;}
        goto done;
    }
    if(argc==4&&!strcmp(argv[1],"identity")){
        char *end;unsigned long p=strtoul(argv[2],&end,10);
        if(cloud_initialized||!argv[2][0]||*end||!p||p>UINT32_MAX)goto invalid;
        unsigned char secret[65]={0};int n=unhex(argv[3],secret,64);
        if(n<1)goto invalid;
        identity.pid=(uint32_t)p;memcpy(identity.secret,secret,sizeof(secret));memset(secret,0,sizeof(secret));
        last_rc=qm_kv_set("armnet/identity",&identity,sizeof(identity),1);goto done;
    }
    if(argc==2&&!strcmp(argv[1],"cloud")){
        if(!identity.pid||!identity.secret[0]||!online)goto invalid;
        if(!cloud_initialized){last_rc=ljyd_cloud_init();if(last_rc)goto done;cloud_initialized=1;ljyd_cloud_set_event_cb(cloud_event,NULL);}
        enabled=1;ljyd_cloud_on_network_up();last_rc=0;goto done;
    }
invalid: qm_cli_printf("\r\nNET_ERROR invalid_or_not_ready\r\n");return;
done: qm_cli_printf("\r\nNET_RESULT rc=%d\r\n",last_rc);status();
}
static const struct qm_cli_command cli={"net_setup","Wi-Fi and explicit team LJYD connection; no remote arm commands",command};
int network_setup_init(void)
{
    /* The diagnostic kernel intentionally skips product KV/Wi-Fi startup.
       Never erase existing settings as recovery from an NVS init failure. */
    int rc=nvs_flash_init();
    if(rc){qm_cli_printf("\r\nNET_INIT_ERROR nvs=%d settings_preserved=1\r\n",rc);return rc;}
    rc=qm_hal_wifi_init();
    if(rc)return rc;
    int n=sizeof(identity);memset(&identity,0,sizeof(identity));
    if(qm_kv_get("armnet/identity",&identity,&n)||n!=sizeof(identity))memset(&identity,0,sizeof(identity));
    identity.secret[64]=0;
    n=sizeof(wifi_enabled);if(qm_kv_get("armnet/wifi",&wifi_enabled,&n)||n!=sizeof(wifi_enabled))wifi_enabled=0;
    rc=qm_event_handler_register(QM_EVENT_WIFI,QM_EVENT_ANY_ID,wifi_event,NULL);
    if(!rc)rc=qm_wifi_init();
    if(!rc)rc=qm_cli_register_command(&cli);
    if(!rc&&wifi_enabled){rc=qm_wifi_set_mode(QM_WIFI_MODE_STA);if(!rc){rc=qm_wifi_start();wifi_started=!rc;}}
    last_rc=rc;qm_cli_printf("\r\nNET_READY version=1 cloud=MANUAL microphone=OFF remote_arm=OFF rc=%d\r\n",rc);return rc;
}

#endif
