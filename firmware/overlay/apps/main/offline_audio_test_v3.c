#include "offline_audio_test.h"
#include "network_setup.h"
#include "actuator_test.h"
#include "lamp_led.h"
#include "camera_test.h"
#include "qm.h"
#if defined(CONFIG_OFFLINE_AUDIO_TEST) && CONFIG_OFFLINE_AUDIO_TEST
#include "qm_cli.h"
#include "qm_work.h"
#include "adapter/qm_audio_device.h"
#include "adapter/qm_audio_device_vb701n_test.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define TAG "audio_test"
#define PCM_CAPACITY 320000u
#define FRAME_BYTES 320u
#define WRITE_TIMEOUT_MS 250u
#define JOB_PLAY (-1)
#define JOB_FIXTURE (-2)
#define JOB_LOOPBACK (-3)
#define JOB_EXPORT (-4)
#define JOB_STOP (-5)
#define JOB_HELLO (-6)
#define JOB_EMOTION_FIRST (-20)
#define IS_EMOTION(j) ((j)<=JOB_EMOTION_FIRST && (j)>=JOB_EMOTION_FIRST-7)
#define JOB_VOLUME_BASE 2000
extern const uint8_t offline_music_pcm_start[] asm("_binary_offline_music_pcm_start");
extern const uint8_t offline_music_pcm_end[] asm("_binary_offline_music_pcm_end");
extern const uint8_t offline_hello_pcm_start[] asm("_binary_offline_hello_pcm_start");
extern const uint8_t offline_hello_pcm_end[] asm("_binary_offline_hello_pcm_end");
extern const uint8_t lamp_robot_slump_start[] asm("_binary_lamp_robot_slump_start");
extern const uint8_t lamp_robot_slump_end[] asm("_binary_lamp_robot_slump_end");
extern const uint8_t lamp_robot_recover_start[] asm("_binary_lamp_robot_recover_start");
extern const uint8_t lamp_robot_recover_end[] asm("_binary_lamp_robot_recover_end");
extern const uint8_t lamp_music_slump_start[] asm("_binary_lamp_music_slump_start");
extern const uint8_t lamp_music_slump_end[] asm("_binary_lamp_music_slump_end");
extern const uint8_t lamp_music_recover_start[] asm("_binary_lamp_music_recover_start");
extern const uint8_t lamp_music_recover_end[] asm("_binary_lamp_music_recover_end");
extern const uint8_t lamp_robot_water_start[] asm("_binary_lamp_robot_water_start");
extern const uint8_t lamp_robot_water_end[] asm("_binary_lamp_robot_water_end");
extern const uint8_t lamp_music_water_start[] asm("_binary_lamp_music_water_start");
extern const uint8_t lamp_music_water_end[] asm("_binary_lamp_music_water_end");
extern const uint8_t lamp_robot_stretch_start[] asm("_binary_lamp_robot_stretch_start");
extern const uint8_t lamp_robot_stretch_end[] asm("_binary_lamp_robot_stretch_end");
extern const uint8_t lamp_music_stretch_start[] asm("_binary_lamp_music_stretch_start");
extern const uint8_t lamp_music_stretch_end[] asm("_binary_lamp_music_stretch_end");
static volatile int s_emotion_state;
static volatile int s_emotion_id=-1;
static uint8_t *s_pcm;
static uint32_t s_retained;
static unsigned s_volume=30;
static QueueHandle_t s_commands;
static void *s_device;
static portMUX_TYPE s_mux=portMUX_INITIALIZER_UNLOCKED;
static int s_busy=1;
static volatile int s_hello_state;
static const char *s_state="INIT";
static volatile int s_cancel;
static SemaphoreHandle_t s_sender_done;
static int s_sender_rc;
static uint32_t s_sender_bytes,s_sender_started,s_sender_finished;
typedef struct { uint64_t square_sum; uint32_t samples,peak,zeros,clipped,frames,timeouts; } signal_stats_t;
static void state(const char *name,int busy) { portENTER_CRITICAL(&s_mux); s_state=name; s_busy=busy; portEXIT_CRITICAL(&s_mux); }
static void retain(uint32_t n) { portENTER_CRITICAL(&s_mux); s_retained=n; portEXIT_CRITICAL(&s_mux); }
static uint32_t fnv32(const uint8_t *p,uint32_t n) { uint32_t h=2166136261u; for(uint32_t i=0;i<n;i++){h=(h^p[i])*16777619u;} return h; }
static void status(void)
{
    const char *name; int busy; uint32_t n; unsigned vol;
    portENTER_CRITICAL(&s_mux); name=s_state; busy=s_busy; n=s_retained; vol=s_volume; portEXIT_CRITICAL(&s_mux);
    QM_LOGI(TAG,"STATUS mode=OFFLINE_PCM revision=3 state=%s busy=%d chip_ready=%d retained_bytes=%lu volume=%u autoplay=OFF hello_state=%d emotion_state=%d emotion_id=%d emotion_count=8",name,busy,qm_vb701n_test_ready(),(unsigned long)n,vol,s_hello_state,s_emotion_state,s_emotion_id);
    QM_LOGI(TAG,"HELP audio_test record 2..10 | play | hello | emotion 0..7 | fixture | loopback | volume 0..100 | export | stop | status");
}
static int number(const char *text,unsigned lo,unsigned hi,int *value)
{
    if(!text || !*text || strlen(text)>3){return 0;}
    for(const char *p=text;*p;p++){if(*p<'0'||*p>'9'){return 0;}}
    unsigned n=(unsigned)strtoul(text,NULL,10); if(n<lo||n>hi){return 0;} *value=(int)n; return 1;
}
static void command(char *out,int out_len,int argc,char **argv)
{
    (void)out;(void)out_len;int job=0,n=0;
    if(argc==1 || (argc==2 && (!strcmp(argv[1],"status")||!strcmp(argv[1],"help")))){status();return;}
    if(argc==2 && !strcmp(argv[1],"stop")){
        s_cancel=1;portENTER_CRITICAL(&s_mux);int busy=s_busy;portEXIT_CRITICAL(&s_mux);
        if(busy){QM_LOGI(TAG,"STOP requested; bounded cleanup pending");return;}job=JOB_STOP;
    }else if(argc==2 && !strcmp(argv[1],"play")){job=JOB_PLAY;
    }else if(argc==2 && !strcmp(argv[1],"hello")){job=JOB_HELLO;
    }else if(argc==3 && !strcmp(argv[1],"emotion") && number(argv[2],0,7,&n)){job=JOB_EMOTION_FIRST-n;
    }else if(argc==2 && !strcmp(argv[1],"fixture")){job=JOB_FIXTURE;
    }else if(argc==2 && !strcmp(argv[1],"loopback")){job=JOB_LOOPBACK;
    }else if(argc==2 && !strcmp(argv[1],"export")){job=JOB_EXPORT;
    }else if(argc==3 && !strcmp(argv[1],"volume") && number(argv[2],0,100,&n)){job=JOB_VOLUME_BASE+n;
    }else if(argc==3 && !strcmp(argv[1],"record") && number(argv[2],2,10,&n)){job=n;
    }else if(argc==2 && number(argv[1],2,10,&n)){job=n;
    }else{QM_LOGW(TAG,"ERROR invalid command; audio_test help");return;}
    portENTER_CRITICAL(&s_mux);
    int reject=s_busy || ((job==JOB_PLAY||job==JOB_EXPORT)&&s_retained==0);
    if(!reject){if(job!=JOB_STOP)s_cancel=0;s_busy=1;s_state="QUEUED";}portEXIT_CRITICAL(&s_mux);
    if(reject){QM_LOGW(TAG,"ERROR busy/not-ready or no retained recording");return;}
    if(job==JOB_HELLO){s_hello_state=1;}
    if(IS_EMOTION(job)){s_emotion_state=1;s_emotion_id=JOB_EMOTION_FIRST-job;}
    if(xQueueSend(s_commands,&job,0)!=pdTRUE){state("READY",0);if(job==JOB_HELLO){s_hello_state=-1;}if(IS_EMOTION(job)){s_emotion_state=-1;}QM_LOGE(TAG,"ERROR queue full");}
    else if(job==JOB_HELLO){QM_LOGI(TAG,"HELLO_QUEUED source=LOCAL_SYNTHESIS");}
    else if(IS_EMOTION(job)){QM_LOGI(TAG,"EMOTION_QUEUED id=%d",s_emotion_id);}
}
static const struct qm_cli_command s_command={"audio_test","Offline audio: music loopback, adjustable volume and checked PCM export",command};
static void add_stats(signal_stats_t *st,const uint8_t *p,uint32_t n)
{
    for(uint32_t i=0;i+1<n;i+=2){
        int32_t x=(int16_t)((uint16_t)p[i]|((uint16_t)p[i+1]<<8));uint32_t a=x<0?(uint32_t)-x:(uint32_t)x;
        st->square_sum+=(uint64_t)((int64_t)x*x);st->samples++;if(a>st->peak){st->peak=a;}if(!a){st->zeros++;}if(a>=32767){st->clipped++;}
    }
}
static int play_buffer(const uint8_t *pcm,uint32_t bytes,const char *source)
{
    static const uint8_t zero[FRAME_BYTES]={0};int ret=qm_vb701n_test_stop();
    if(ret!=QM_EOK||!bytes){return -QM_EIO;}
    ret=qm_audio_device_set_volume(s_device,(uint8_t)s_volume);if(ret!=QM_EOK){return ret;}
    state("PLAYING",1);QM_LOGI(TAG,"PLAYING source=%s bytes=%lu volume=%u microphone=STOPPED",source,(unsigned long)bytes,s_volume);
    uint32_t sent=0,started=qm_now_ms(),limit=bytes/32u+4000u;TickType_t tick=xTaskGetTickCount();
    for(unsigned i=0;i<20&&ret==QM_EOK&&!s_cancel;i++){ret=qm_vb701n_test_write(zero,sizeof(zero),WRITE_TIMEOUT_MS);vTaskDelayUntil(&tick,pdMS_TO_TICKS(10));}
    while(ret==QM_EOK&&sent<bytes&&!s_cancel&&qm_now_ms()-started<limit){
        uint32_t n=bytes-sent;if(n>FRAME_BYTES){n=FRAME_BYTES;}ret=qm_vb701n_test_write(pcm+sent,n,WRITE_TIMEOUT_MS);
        if(ret==QM_EOK){sent+=n;}vTaskDelayUntil(&tick,pdMS_TO_TICKS(10));
    }
    if(ret==QM_EOK&&sent!=bytes){ret=-QM_ETIMEOUT;}
    for(unsigned i=0;i<20&&ret==QM_EOK&&!s_cancel;i++){ret=qm_vb701n_test_write(zero,sizeof(zero),WRITE_TIMEOUT_MS);vTaskDelayUntil(&tick,pdMS_TO_TICKS(10));}
    if(ret==QM_EOK&&!s_cancel){vTaskDelay(pdMS_TO_TICKS(250));}int stopped=qm_vb701n_test_stop();
    QM_LOGI(TAG,"PLAYBACK submitted_bytes=%lu elapsed_ms=%lu volume=%u rc=%d stop_rc=%d completion=HOST_TIMED_NO_CHIP_ACK",(unsigned long)sent,(unsigned long)(qm_now_ms()-started),s_volume,ret,stopped);
    return ret==QM_EOK?stopped:ret;
}
/* Capture owns start/stop. This task only transmits the known source, never
 * microphone data, so no closed-loop software feedback is introduced. */
static void fixture_sender(void *arg)
{
    (void)arg;static const uint8_t zero[FRAME_BYTES]={0};
    uint32_t size=(uint32_t)(offline_music_pcm_end-offline_music_pcm_start);TickType_t tick=xTaskGetTickCount();
    s_sender_started=qm_now_ms();s_sender_rc=QM_EOK;s_sender_bytes=0;
    for(unsigned i=0;i<20&&s_sender_rc==QM_EOK&&!s_cancel;i++){s_sender_rc=qm_vb701n_test_duplex_write(zero,sizeof(zero),WRITE_TIMEOUT_MS);vTaskDelayUntil(&tick,pdMS_TO_TICKS(10));}
    while(s_sender_rc==QM_EOK&&s_sender_bytes<size&&!s_cancel&&qm_now_ms()-s_sender_started<12000u){
        uint32_t n=size-s_sender_bytes;if(n>FRAME_BYTES){n=FRAME_BYTES;}
        s_sender_rc=qm_vb701n_test_duplex_write(offline_music_pcm_start+s_sender_bytes,n,WRITE_TIMEOUT_MS);
        if(s_sender_rc==QM_EOK){s_sender_bytes+=n;}vTaskDelayUntil(&tick,pdMS_TO_TICKS(10));
    }
    if(s_sender_rc==QM_EOK&&s_sender_bytes!=size){s_sender_rc=-QM_ETIMEOUT;}
    for(unsigned i=0;i<20&&s_sender_rc==QM_EOK&&!s_cancel;i++){s_sender_rc=qm_vb701n_test_duplex_write(zero,sizeof(zero),WRITE_TIMEOUT_MS);vTaskDelayUntil(&tick,pdMS_TO_TICKS(10));}
    s_sender_finished=qm_now_ms();xSemaphoreGive(s_sender_done);vTaskDelete(NULL);
}
static int record_sample(unsigned seconds,int duplex)
{
    signal_stats_t st={0};uint8_t frame[512];uint32_t used=0,target=seconds*32000u,started=qm_now_ms();
    int ret=QM_EOK,joined=1;TaskHandle_t sender;retain(0);state(duplex?"LOOPBACK":"RECORDING",1);
    ret=qm_vb701n_test_stop();if(ret==QM_EOK){ret=qm_audio_device_set_volume(s_device,(uint8_t)s_volume);}if(ret!=QM_EOK){return ret;}
    QM_LOGI(TAG,"RECORDING seconds=%u target_bytes=%lu pcm=16000Hz/mono/S16LE speaker=%s volume=%u",seconds,(unsigned long)target,duplex?"FIXTURE_CONCURRENT":"OFF",s_volume);
    ret=qm_vb701n_test_record_start();
    if(ret==QM_EOK&&duplex){
        while(xSemaphoreTake(s_sender_done,0)==pdTRUE){}
        if(xTaskCreate(fixture_sender,"fixture_tx",4096,NULL,8,&sender)!=pdPASS){ret=-QM_ENOMEM;}else{joined=0;}
    }
    while(ret==QM_EOK&&used<target&&!s_cancel&&qm_now_ms()-started<seconds*1000u+2000u){
        uint32_t n=0;ret=qm_vb701n_test_record_read(frame,sizeof(frame),&n,100);
        if(ret==-QM_ETIMEOUT){st.timeouts++;ret=QM_EOK;continue;}if(ret!=QM_EOK){break;}
        if(n>target-used){n=target-used;}memcpy(s_pcm+used,frame,n);add_stats(&st,frame,n);st.frames++;used+=n;
    }
    if(!joined){
        if(xSemaphoreTake(s_sender_done,pdMS_TO_TICKS(1000))!=pdTRUE){
            s_cancel=1;if(xSemaphoreTake(s_sender_done,pdMS_TO_TICKS(500))!=pdTRUE){state("ERROR_SENDER",1);QM_LOGE(TAG,"ERROR sender did not join; fail closed");return -QM_ETIMEOUT;}
        }joined=1;
    }
    int stopped=qm_vb701n_test_stop();uint32_t drops=qm_vb701n_test_drops();if(used){retain(used);}
    QM_LOGI(TAG,"CAPTURE bytes=%lu samples=%lu frames=%lu elapsed_ms=%lu rms=%.2f peak=%lu",(unsigned long)used,(unsigned long)st.samples,(unsigned long)st.frames,(unsigned long)(qm_now_ms()-started),st.samples?sqrt((double)st.square_sum/st.samples):0.0,(unsigned long)st.peak);
    QM_LOGI(TAG,"SIGNAL zeros=%lu clipped=%lu read_timeouts=%lu queue_drops=%lu stop_rc=%d complete=%d nonzero=%d",(unsigned long)st.zeros,(unsigned long)st.clipped,(unsigned long)st.timeouts,(unsigned long)drops,stopped,used==target,st.peak!=0);
    if(duplex){QM_LOGI(TAG,"DUPLEX fixture_bytes=%lu fixture_rc=%d sender_start_ms=%lu sender_end_ms=%lu capture_start_ms=%lu expected_fixture_bytes=256000",(unsigned long)s_sender_bytes,s_sender_rc,(unsigned long)s_sender_started,(unsigned long)s_sender_finished,(unsigned long)started);if(s_sender_rc!=QM_EOK){ret=s_sender_rc;}}
    QM_LOGI(TAG,"HELD source=MIC_PCM bytes=%lu playback=NOT_REQUESTED export=AVAILABLE",(unsigned long)used);
    if(stopped!=QM_EOK){return stopped;}if(used!=target||drops||s_cancel){return -QM_EIO;}return ret;
}
static int export_sample(void)
{
    uint32_t bytes=s_retained;if(!bytes||bytes>PCM_CAPACITY){return -QM_EINVAL;}state("EXPORTING",1);uint32_t hash=fnv32(s_pcm,bytes);
    qm_cli_printf("\r\nAUDIO_BEGIN %lu 16000 1 16 %08lx\r\n",(unsigned long)bytes,(unsigned long)hash);
    static const char digits[]="0123456789abcdef";
    for(uint32_t off=0;off<bytes&&!s_cancel;){
        char hex[193];uint32_t n=bytes-off;if(n>96){n=96;}
        for(uint32_t i=0;i<n;i++){uint8_t b=s_pcm[off+i];hex[2*i]=digits[b>>4];hex[2*i+1]=digits[b&15];}hex[n*2]=0;
        qm_cli_printf("AUDIO_DATA %lu %s\r\n",(unsigned long)off,hex);off+=n;if(!(off%3072u)){vTaskDelay(1);}
    }
    if(s_cancel){qm_cli_printf("AUDIO_ABORT cancelled\r\n");return -QM_EINTR;}
    qm_cli_printf("AUDIO_END %lu %08lx\r\n",(unsigned long)bytes,(unsigned long)hash);return QM_EOK;
}
static void worker(void *arg)
{
    (void)arg;uint32_t started=qm_now_ms();
    while(!qm_vb701n_test_ready()&&qm_now_ms()-started<20000u){vTaskDelay(pdMS_TO_TICKS(50));}
    if(!qm_vb701n_test_ready()||qm_vb701n_test_stop()!=QM_EOK||qm_audio_device_set_volume(s_device,(uint8_t)s_volume)!=QM_EOK){state("ERROR_CHIP_NOT_READY",1);QM_LOGE(TAG,"ERROR audio module not ready");vTaskDelete(NULL);return;}
    state("READY",0);QM_LOGI(TAG,"READY revision=3 recording=OFF speaker=OFF autoplay=OFF fixture=Carefree_8s export=FNV32_HEX");
    for(;;){
        int job=0,ret=QM_EOK;xQueueReceive(s_commands,&job,portMAX_DELAY);
        if(job>0&&job<=10){ret=record_sample((unsigned)job,0);
        }else if(job==JOB_LOOPBACK){ret=record_sample(10,1);
        }else if(job==JOB_PLAY){ret=play_buffer(s_pcm,s_retained,"RETAINED_MIC_PCM");
        }else if(job==JOB_HELLO){ret=play_buffer(offline_hello_pcm_start,(uint32_t)(offline_hello_pcm_end-offline_hello_pcm_start),"GENERATED_HELLO");
        }else if(IS_EMOTION(job)){
            const uint8_t *pcm=NULL;uint32_t bytes=0;
            switch(JOB_EMOTION_FIRST-job){
        case 0: pcm=lamp_robot_slump_start;bytes=(uint32_t)(lamp_robot_slump_end-lamp_robot_slump_start);break;
        case 1: pcm=lamp_robot_recover_start;bytes=(uint32_t)(lamp_robot_recover_end-lamp_robot_recover_start);break;
        case 2: pcm=lamp_music_slump_start;bytes=(uint32_t)(lamp_music_slump_end-lamp_music_slump_start);break;
        case 3: pcm=lamp_music_recover_start;bytes=(uint32_t)(lamp_music_recover_end-lamp_music_recover_start);break;
        case 4: pcm=lamp_robot_water_start;bytes=(uint32_t)(lamp_robot_water_end-lamp_robot_water_start);break;
        case 5: pcm=lamp_music_water_start;bytes=(uint32_t)(lamp_music_water_end-lamp_music_water_start);break;
        case 6: pcm=lamp_robot_stretch_start;bytes=(uint32_t)(lamp_robot_stretch_end-lamp_robot_stretch_start);break;
        case 7: pcm=lamp_music_stretch_start;bytes=(uint32_t)(lamp_music_stretch_end-lamp_music_stretch_start);break;
            }
            ret=pcm?play_buffer(pcm,bytes,"ORIGINAL_LAMP_EMOTION"):-QM_EINVAL;
        }else if(job==JOB_FIXTURE){ret=play_buffer(offline_music_pcm_start,(uint32_t)(offline_music_pcm_end-offline_music_pcm_start),"LICENSED_CAREFREE_FIXTURE");
        }else if(job==JOB_EXPORT){ret=export_sample();
        }else if(job==JOB_STOP){ret=qm_vb701n_test_stop();
        }else if(job>=JOB_VOLUME_BASE&&job<=JOB_VOLUME_BASE+100){
            unsigned selected=(unsigned)(job-JOB_VOLUME_BASE);ret=qm_audio_device_set_volume(s_device,(uint8_t)selected);
            if(ret==QM_EOK){portENTER_CRITICAL(&s_mux);s_volume=selected;portEXIT_CRITICAL(&s_mux);}QM_LOGI(TAG,"VOLUME requested=%u actual=%u hardware_max=31 rc=%d",selected,s_volume,ret);
        }else{ret=-QM_EINVAL;}
        /* A sender that did not join is not safe to race with a stop packet. */
        if(!strcmp(s_state,"ERROR_SENDER")){QM_LOGE(TAG,"ERROR worker fail-closed; reset required");vTaskDelete(NULL);return;}
        int stopped=qm_vb701n_test_stop();QM_LOGI(TAG,"DONE job=%d result=%s rc=%d stop_rc=%d retained_bytes=%lu recording=OFF speaker=OFF",job,ret==QM_EOK&&stopped==QM_EOK?"HOST_OK":"ERROR",ret,stopped,(unsigned long)s_retained);
        if(job==JOB_HELLO){s_hello_state=(ret==QM_EOK&&stopped==QM_EOK&&!s_cancel)?2:-1;}
        if(IS_EMOTION(job)){s_emotion_state=(ret==QM_EOK&&stopped==QM_EOK&&!s_cancel)?2:-1;}
        if(stopped!=QM_EOK){state("ERROR_STOP",1);}else{state("READY",0);QM_LOGI(TAG,"READY recording=OFF speaker=OFF autoplay=OFF");}
    }
}
void offline_audio_test_start(void)
{
    qm_audio_device_config_t config={0};TaskHandle_t task;
    QM_LOGI(TAG,"BOOT mode=OFFLINE_PCM revision=bebdc802 test=3 NETWORK_SETUP_EXPLICIT NO_POSE ACTUATORS_COMMAND_ONLY NO_BOOT_SOUND NO_AUTORECORD NO_AUTOPLAY DUPLEX_FIXTURE EXPORT VOLUME");
    uint32_t fixture=(uint32_t)(offline_music_pcm_end-offline_music_pcm_start);if(fixture!=256000u||fixture%FRAME_BYTES){QM_LOGE(TAG,"ERROR fixture length");return;}
    s_pcm=heap_caps_malloc(PCM_CAPACITY,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);s_commands=xQueueCreate(1,sizeof(int));s_sender_done=xSemaphoreCreateBinary();
    if(!s_pcm||!s_commands||!s_sender_done||qm_work_on_init()!=QM_EOK){QM_LOGE(TAG,"ERROR allocation/init");return;}
    if(qm_audio_device_open(&s_device,&config)!=QM_EOK||qm_audio_device_set_volume(s_device,(uint8_t)s_volume)!=QM_EOK){QM_LOGE(TAG,"ERROR adapter init");return;}
    if(qm_cli_init()!=QM_EOK||qm_cli_register_command(&s_command)!=QM_EOK){QM_LOGE(TAG,"ERROR CLI init");return;}
    if(actuator_test_init()!=ESP_OK){QM_LOGE(TAG,"ERROR actuator init; outputs remain off");return;}
    if(camera_test_init()!=ESP_OK){QM_LOGE(TAG,"ERROR camera CLI init");return;}
    if(xTaskCreate(worker,"offline_audio",8192,NULL,8,&task)!=pdPASS){QM_LOGE(TAG,"ERROR worker allocation");return;}
    if(lamp_led_cli_init()!=QM_EOK){QM_LOGE(TAG,"ERROR LED CLI init");}
    network_setup_init();
    QM_LOGI(TAG,"INIT PSRAM=%lu fixture_bytes=%lu fixture_fnv32=%08lx volume=%u UART0=115200",(unsigned long)PCM_CAPACITY,(unsigned long)fixture,(unsigned long)fnv32(offline_music_pcm_start,fixture),s_volume);
}
#endif
