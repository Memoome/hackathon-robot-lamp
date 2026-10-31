#include "wireless.h"
#include "qm.h"
#include "qm_cli.h"
#include "esp_http_server.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_mac.h"
#include "nvs.h"
#include "mbedtls/sha256.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static char key[65],reply[4096];
static size_t used;
static TaskHandle_t owner;
static httpd_handle_t server;
int lamp_reply(const char *fmt,...) {
    char buf[768];va_list ap;va_start(ap,fmt);vsnprintf(buf,sizeof(buf),fmt,ap);va_end(ap);
    if(owner==xTaskGetCurrentTaskHandle()){
        if(used>=sizeof(reply)-2)return 0;
        size_t n=strlen(buf);if(n>sizeof(reply)-used-2)n=sizeof(reply)-used-2;
        memcpy(reply+used,buf,n);used+=n;reply[used++]='\n';reply[used]=0;
    } else qm_cli_printf("%s\r\n",buf);
    return 0;
}
static int authorized(httpd_req_t *r) {
    char provided[65];if(!key[0]||httpd_req_get_hdr_value_str(r,"X-Lamp-Key",provided,sizeof(provided))!=ESP_OK)return 0;
    if(strlen(provided)!=64)return 0;
    unsigned diff=0;for(int i=0;i<64;i++)diff|=(unsigned char)provided[i]^(unsigned char)key[i];return diff==0;
}
static esp_err_t deny(httpd_req_t*r,const char*status,const char*text){httpd_resp_set_status(r,status);return httpd_resp_sendstr(r,text);}
static esp_err_t command_http(httpd_req_t*r) {
    if(!authorized(r))return deny(r,"403 Forbidden","Pairing key required");
    if(r->content_len<1||r->content_len>200)return deny(r,"400 Bad Request","Command length");
    char line[201];int n=0;while(n<r->content_len){int k=httpd_req_recv(r,line+n,r->content_len-n);if(k<=0)return ESP_FAIL;n+=k;}line[n]=0;
    for(int i=0;i<n;i++)if(!((line[i]>='a'&&line[i]<='z')||(line[i]>='0'&&line[i]<='9')||line[i]==' '||line[i]=='_'||line[i]=='-'))return deny(r,"400 Bad Request","Invalid characters");
    char *argv[8],*save;int argc=0;char*p=strtok_r(line," ",&save);
    while(p){if(argc==8)return deny(r,"400 Bad Request","Too many arguments");argv[argc++]=p;p=strtok_r(NULL," ",&save);}
    if(argc<2)return deny(r,"400 Bad Request","Missing command");
    used=0;reply[0]=0;owner=xTaskGetCurrentTaskHandle();
    if(!strcmp(argv[0],"arm_live"))lamp_remote_arm(argc,argv);
    else if(!strcmp(argv[0],"lamp_led"))lamp_remote_led(argc,argv);
    else if(!strcmp(argv[0],"audio_test")&&(!strcmp(argv[1],"status")||!strcmp(argv[1],"volume")||!strcmp(argv[1],"emotion")||!strcmp(argv[1],"hello")||!strcmp(argv[1],"stop")))lamp_remote_audio(argc,argv);
    else lamp_reply("ERROR command not allowed over Wi-Fi");
    owner=NULL;httpd_resp_set_type(r,"text/plain");return httpd_resp_sendstr(r,reply);
}
static void restart_task(void*p){vTaskDelay(pdMS_TO_TICKS(1000));esp_restart();}
static esp_err_t update_http(httpd_req_t*r) {
    if(!authorized(r))return deny(r,"403 Forbidden","Pairing key required");
    const esp_partition_t*part=esp_ota_get_next_update_partition(NULL);
    if(!part||r->content_len<1024||(unsigned)r->content_len>part->size)return deny(r,"400 Bad Request","Image size");
    char wanted[65];if(httpd_req_get_hdr_value_str(r,"X-Image-SHA256",wanted,sizeof(wanted))!=ESP_OK||strlen(wanted)!=64)return deny(r,"400 Bad Request","SHA256 required");
    if(!lamp_update_gate(1))return deny(r,"409 Conflict","Release all servo outputs before updating");
    esp_ota_handle_t ota=0;esp_err_t rc=esp_ota_begin(part,r->content_len,&ota);
    mbedtls_sha256_context sha;mbedtls_sha256_init(&sha);mbedtls_sha256_starts(&sha,0);
    char buf[2048];int left=r->content_len;
    while(rc==ESP_OK&&left>0){int n=httpd_req_recv(r,buf,left>(int)sizeof(buf)?sizeof(buf):left);if(n<=0){rc=ESP_FAIL;break;}mbedtls_sha256_update(&sha,(unsigned char*)buf,n);rc=esp_ota_write(ota,buf,n);left-=n;}
    unsigned char digest[32];char hex[65];mbedtls_sha256_finish(&sha,digest);mbedtls_sha256_free(&sha);for(int i=0;i<32;i++)sprintf(hex+2*i,"%02x",digest[i]);
    if(rc==ESP_OK&&strcmp(hex,wanted))rc=ESP_FAIL;
    if(rc==ESP_OK){rc=esp_ota_end(ota);ota=0;}
    if(ota)esp_ota_abort(ota);
    if(rc==ESP_OK)rc=esp_ota_set_boot_partition(part);
    if(rc!=ESP_OK){lamp_update_gate(0);return deny(r,"400 Bad Request","Upload rejected; current firmware retained");}
    httpd_resp_sendstr(r,"UPDATE_OK restarting outputs_off=1");xTaskCreate(restart_task,"ota_restart",2048,NULL,3,NULL);return ESP_OK;
}
static void discovery(void*p) {
    int fd=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);struct sockaddr_in addr={.sin_family=AF_INET,.sin_port=htons(45832),.sin_addr.s_addr=htonl(INADDR_ANY)};
    if(fd<0||bind(fd,(void*)&addr,sizeof(addr))<0){if(fd>=0)close(fd);vTaskDelete(NULL);return;}
    for(;;){char b[64];struct sockaddr_in peer;socklen_t len=sizeof(peer);int n=recvfrom(fd,b,sizeof(b)-1,0,(void*)&peer,&len);if(n!=16||memcmp(b,"LAMP_DISCOVER_V1",16))continue;
        unsigned char mac[6];esp_read_mac(mac,ESP_MAC_WIFI_STA);char msg[100];snprintf(msg,sizeof(msg),"LAMP_V1 %02x%02x%02x%02x%02x%02x 8032",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);sendto(fd,msg,strlen(msg),0,(void*)&peer,len);}
}
static void cli(char*out,int len,int argc,char**argv) {
    if(argc==3&&!strcmp(argv[1],"pair")&&strlen(argv[2])==64){
        for(int i=0;i<64;i++)if(!((argv[2][i]>='0'&&argv[2][i]<='9')||(argv[2][i]>='a'&&argv[2][i]<='f'))){qm_cli_printf("WIRELESS_ERROR invalid_key\r\n");return;}
        nvs_handle_t h;if(nvs_open("lamp_wireless",NVS_READWRITE,&h)==ESP_OK){esp_err_t rc=nvs_set_str(h,"key",argv[2]);if(rc==ESP_OK)rc=nvs_commit(h);nvs_close(h);if(rc==ESP_OK)memcpy(key,argv[2],65);qm_cli_printf("WIRELESS_PAIR rc=%d\r\n",rc);}return;
    }
    qm_cli_printf("WIRELESS_STATUS version=1 paired=%d port=8032 ota=1\r\n",key[0]!=0);
}
void lamp_wireless_init(void) {
    nvs_handle_t h;size_t n=sizeof(key);if(nvs_open("lamp_wireless",NVS_READONLY,&h)==ESP_OK){if(nvs_get_str(h,"key",key,&n)!=ESP_OK)key[0]=0;nvs_close(h);}
    static const struct qm_cli_command c={"lamp_wireless","USB pairing and wireless status",cli};qm_cli_register_command(&c);
    httpd_config_t cfg=HTTPD_DEFAULT_CONFIG();cfg.server_port=8032;cfg.stack_size=8192;cfg.recv_wait_timeout=5;
    if(httpd_start(&server,&cfg)==ESP_OK){httpd_uri_t a={.uri="/command",.method=HTTP_POST,.handler=command_http},b={.uri="/update",.method=HTTP_POST,.handler=update_http};httpd_register_uri_handler(server,&a);httpd_register_uri_handler(server,&b);}
    xTaskCreate(discovery,"lamp_discovery",3072,NULL,3,NULL);
}
