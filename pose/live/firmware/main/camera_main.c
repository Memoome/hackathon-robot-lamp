#include "pose_engine.h"
#include "detect_engine.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include "esp_log.h"
#include "esp_psram.h"
#include "driver/gpio.h"
#include "driver/gpio_filter.h"
#include "driver/spi_master.h"
#include "esp_cam_ctlr_spi.h"
#include "esp_cam_sensor_xclk.h"
#include "esp_video_init.h"
#include "esp_video_device.h"
#include "esp_video_ioctl.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <unistd.h>

#define TAG "cam_test"
static QueueHandle_t jobs;
static portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
static volatile int busy,cancelled,detected;
static int initialized,last_error;
static int rotation=90;
static unsigned sequence;
static uint32_t width,height,fourcc;
static gpio_glitch_filter_handle_t vsync_filter;
// BF3901 stores this format pointer; it must outlive every capture.
static esp_cam_sensor_format_t sensor_format;
#define THUMB_BYTES (120*160*2)
static volatile int preview_every,preview_busy;
static uint8_t *preview_data;
static unsigned preview_seq;
static TaskHandle_t preview_task_handle;

static void status(void)
{
    ESP_LOGI(TAG,"CAM_STATUS version=1 busy=%d detected=%d width=%lu height=%lu pclk=9 sda=21 scl=47 cs=4 data=8 pwdn=41 error=%d",busy,detected,(unsigned long)width,(unsigned long)height,last_error);
}

static esp_err_t setup_video(void)
{
    if(initialized) return ESP_OK;
    gpio_config_t g={.pin_bit_mask=1ULL<<41,.mode=GPIO_MODE_OUTPUT,
        .pull_up_en=GPIO_PULLUP_DISABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
    esp_err_t err=gpio_config(&g);
    if(err!=ESP_OK) return err;
    gpio_set_level(41,1);vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(41,0);vTaskDelay(pdMS_TO_TICKS(100));
    const esp_video_init_spi_config_t spi={
        .sccb_config={.init_sccb=true,.i2c_config={.port=0,.scl_pin=47,.sda_pin=21},.freq=100000},
        .intf=ESP_CAM_CTLR_SPI_CAM_INTF_SPI,.io_mode=ESP_CAM_CTLR_SPI_CAM_IO_MODE_1BIT,
        .spi_port=SPI2_HOST,.spi_cs_pin=4,.spi_sclk_pin=9,.spi_data0_io_pin=8,
        .spi_data1_io_pin=-1,.spi_data2_io_pin=-1,.spi_data3_io_pin=-1,
        .reset_pin=-1,.pwdn_pin=-1,.xclk_source=ESP_CAM_SENSOR_XCLK_LEDC,.xclk_freq=0,.xclk_pin=-1
    };
    const esp_video_init_config_t config={.spi=&spi};
    err=esp_video_init(&config);
    if(err!=ESP_OK) {esp_video_deinit();return err;}
    initialized=1;
    return ESP_OK;
}

static uint32_t fnv32(const uint8_t *p,uint32_t n)
{
    uint32_t h=2166136261u;
    for(uint32_t i=0;i<n;i++)h=(h^p[i])*16777619u;
    return h;
}

// stdout is unbuffered, so printf issues several writes; two tasks would interleave mid-line.
static void out_line(const char *fmt,...)
{
    char buf[320];
    va_list ap;va_start(ap,fmt);
    int n=vsnprintf(buf,sizeof(buf),fmt,ap);
    va_end(ap);
    if(n<0)return;
    if(n>=(int)sizeof(buf))n=sizeof(buf)-1;
    fwrite(buf,1,n,stdout);
}

// Downscale a 240x320 frame to a 120x160 UYVY thumbnail.
static void make_thumb(const uint8_t *src,uint8_t *thumb)
{
    for(unsigned y=0;y<160;y++) for(unsigned x=0;x<120;x+=2) {
        const uint8_t *a=src+(y*2*width+x*2)*2;
        uint8_t *d=thumb+(y*120+x)*2;
        if(fourcc==V4L2_PIX_FMT_UYVY) {
            d[0]=((unsigned)a[0]+a[4])/2;d[1]=a[1];
            d[2]=((unsigned)a[2]+a[6])/2;d[3]=a[5];
        } else {
            d[0]=((unsigned)a[1]+a[5])/2;d[1]=a[0];
            d[2]=((unsigned)a[3]+a[7])/2;d[3]=a[4];
        }
    }
}

static void send_hex(const uint8_t *data,uint32_t n)
{
    const char hexchars[]="0123456789abcdef";
    for(uint32_t off=0;off<n && !cancelled;) {
        char hex[193];uint32_t count=n-off;if(count>96)count=96;
        for(uint32_t i=0;i<count;i++){uint8_t c=data[off+i];hex[2*i]=hexchars[c>>4];hex[2*i+1]=hexchars[c&15];}
        hex[count*2]=0;out_line("CAM_DATA %lu %s\r\n",(unsigned long)off,hex);
        off+=count;if(!(off%3072u))vTaskDelay(1);
    }
}

// Sends stream previews on its own task so detection keeps running during the transfer.
static void preview_task(void *arg)
{
    (void)arg;
    for(;;) {
        ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
        uint32_t hash=fnv32(preview_data,THUMB_BYTES);
        out_line("PREVIEW_BEGIN %u %u 120 160 UYVY %08lx\r\n",preview_seq,THUMB_BYTES,(unsigned long)hash);
        send_hex(preview_data,THUMB_BYTES);
        if(cancelled)out_line("PREVIEW_ABORT %u\r\n",preview_seq);
        else out_line("PREVIEW_END %u %u %08lx\r\n",preview_seq,THUMB_BYTES,(unsigned long)hash);
        preview_busy=0;
    }
}

static esp_err_t stream(void)
{
    int fd=-1,streaming=0;
    uint8_t *buffers[2]={0};
    size_t sizes[2]={0};
    esp_err_t err=setup_video();
    if(err!=ESP_OK) return err;
    fd=open(ESP_VIDEO_SPI_DEVICE_NAME,O_RDWR);
    if(fd<0) return ESP_FAIL;
    if(ioctl(fd,VIDIOC_G_SENSOR_FMT,&sensor_format)!=0 ||
       ioctl(fd,VIDIOC_S_SENSOR_FMT,&sensor_format)!=0) {err=ESP_FAIL;goto done;}
    struct v4l2_format fmt={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE};
    if(ioctl(fd,VIDIOC_G_FMT,&fmt)!=0){err=ESP_FAIL;goto done;}
    width=fmt.fmt.pix.width;height=fmt.fmt.pix.height;fourcc=fmt.fmt.pix.pixelformat;
    detected=1;
    if((fourcc!=V4L2_PIX_FMT_UYVY && fourcc!=V4L2_PIX_FMT_YUYV) || width!=240 || height!=320) {err=ESP_ERR_NOT_SUPPORTED;goto done;}
    struct v4l2_requestbuffers req={.count=2,.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};
    if(ioctl(fd,VIDIOC_REQBUFS,&req)!=0 || req.count!=2){err=ESP_FAIL;goto done;}
    for(int i=0;i<2;i++) {
        struct v4l2_buffer b={.index=i,.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};
        if(ioctl(fd,VIDIOC_QUERYBUF,&b)!=0){err=ESP_FAIL;goto done;}
        sizes[i]=b.length;
        buffers[i]=mmap(NULL,b.length,PROT_READ|PROT_WRITE,MAP_SHARED,fd,b.m.offset);
        if(buffers[i]==MAP_FAILED){buffers[i]=NULL;err=ESP_FAIL;goto done;}
        if(ioctl(fd,VIDIOC_QBUF,&b)!=0){err=ESP_FAIL;goto done;}
    }
    struct timeval timeout={.tv_sec=1,.tv_usec=0};
    if(ioctl(fd,VIDIOC_S_DQBUF_TIMEOUT,&timeout)!=0){err=ESP_FAIL;goto done;}
    int type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if(ioctl(fd,VIDIOC_STREAMON,&type)!=0){err=ESP_FAIL;goto done;}
    streaming=1;
    ESP_LOGI(TAG,"STREAM_START width=%lu height=%lu fourcc=%08lx preview_every=%d warmup_frames=3",(unsigned long)width,(unsigned long)height,(unsigned long)fourcc,preview_every);
    int warm=0;
    unsigned valid=0,bad=0,dq_fail=0,dets=0,previews=0,skipped=0;
    int64_t last_valid=esp_timer_get_time(),last_det=0,stats_at=last_valid+5000000;
    while(!cancelled) {
        int64_t now=esp_timer_get_time();
        if(now-last_valid>3000000){err=ESP_ERR_TIMEOUT;break;}
        if(now>=stats_at) {
            out_line("STREAM_STATS {\"valid\":%u,\"bad\":%u,\"dq_fail\":%u,\"det\":%u,\"preview\":%u,\"preview_skipped\":%u,\"psram_free\":%u}\r\n",
                   valid,bad,dq_fail,dets,previews,skipped,(unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
            stats_at=now+5000000;
        }
        struct v4l2_buffer b={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};
        if(ioctl(fd,VIDIOC_DQBUF,&b)!=0){++dq_fail;continue;}
        int ok=b.index<2 && b.bytesused==width*height*2 && b.bytesused<=sizes[b.index];
        if(ok) {
            last_valid=esp_timer_get_time();
            ++valid;
            if(warm<3) ++warm;
            else {
                const uint8_t *src=buffers[b.index];
                ++sequence;
                if(preview_every>0 && sequence%preview_every==0) {
                    if(preview_busy) ++skipped;
                    else {
                        make_thumb(src,preview_data);
                        preview_seq=sequence;preview_busy=1;++previews;
                        xTaskNotifyGive(preview_task_handle);
                    }
                }
                double cycle=last_det?(last_valid-last_det)/1000.0:0;
                err=detect_engine_stream(src,width,height,fourcc,rotation,sequence,last_valid/1000,cycle);
                last_det=last_valid;
                ++dets;
            }
        } else ++bad;
        if(ioctl(fd,VIDIOC_QBUF,&b)!=0){err=ESP_FAIL;break;}
        if(err!=ESP_OK)break;
        // Let the idle task run; DQBUF may not block when a frame is already queued.
        vTaskDelay(1);
    }
    ESP_LOGI(TAG,"STREAM_STOP valid=%u bad=%u dq_fail=%u det=%u preview=%u preview_skipped=%u",valid,bad,dq_fail,dets,previews,skipped);
done:
    if(fd>=0) {
        if(streaming){int t=V4L2_BUF_TYPE_VIDEO_CAPTURE;ioctl(fd,VIDIOC_STREAMOFF,&t);}
        for(int i=0;i<2;i++)if(buffers[i])munmap(buffers[i],sizes[i]);
        close(fd);
    }
    // Do not report done while a preview is still being printed.
    for(int i=0;preview_busy && i<300;i++)vTaskDelay(pdMS_TO_TICKS(10));
    return err;
}

static esp_err_t operate(int job)
{
    int capture=job!=1;
    int fd=-1,streaming=0;
    uint8_t *buffers[2]={0},*thumb=NULL,*raw=NULL;
    size_t sizes[2]={0};
    esp_err_t err=setup_video();
    if(err!=ESP_OK) return err;
    fd=open(ESP_VIDEO_SPI_DEVICE_NAME,O_RDWR);
    if(fd<0) return ESP_FAIL;
    if(capture) {
        if(ioctl(fd,VIDIOC_G_SENSOR_FMT,&sensor_format)!=0 ||
           ioctl(fd,VIDIOC_S_SENSOR_FMT,&sensor_format)!=0) {err=ESP_FAIL;goto done;}
        ESP_LOGI(TAG,"FRAME_CONFIG_REFRESH applied_before_streamon=1");
    }
    struct v4l2_format fmt={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE};
    if(ioctl(fd,VIDIOC_G_FMT,&fmt)!=0){err=ESP_FAIL;goto done;}
    width=fmt.fmt.pix.width;height=fmt.fmt.pix.height;fourcc=fmt.fmt.pix.pixelformat;
    detected=1;
    ESP_LOGI(TAG,"CAM_PROBE_OK sensor=BF3901 width=%lu height=%lu fourcc=%08lx pclk=9 xclk=ONBOARD",(unsigned long)width,(unsigned long)height,(unsigned long)fourcc);
    if(!capture) {err=ESP_OK;goto done;}
    if((fourcc!=V4L2_PIX_FMT_UYVY && fourcc!=V4L2_PIX_FMT_YUYV) || width!=240 || height!=320) {err=ESP_ERR_NOT_SUPPORTED;goto done;}
    thumb=heap_caps_malloc(120*160*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    raw=heap_caps_malloc(width*height*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!thumb || !raw){err=ESP_ERR_NO_MEM;goto done;}
    struct v4l2_requestbuffers req={.count=2,.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};
    if(ioctl(fd,VIDIOC_REQBUFS,&req)!=0 || req.count!=2){err=ESP_FAIL;goto done;}
    for(int i=0;i<2;i++) {
        struct v4l2_buffer b={.index=i,.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};
        if(ioctl(fd,VIDIOC_QUERYBUF,&b)!=0){err=ESP_FAIL;goto done;}
        sizes[i]=b.length;
        buffers[i]=mmap(NULL,b.length,PROT_READ|PROT_WRITE,MAP_SHARED,fd,b.m.offset);
        if(buffers[i]==MAP_FAILED){buffers[i]=NULL;err=ESP_FAIL;goto done;}
        if(ioctl(fd,VIDIOC_QBUF,&b)!=0){err=ESP_FAIL;goto done;}
    }
    struct timeval timeout={.tv_sec=1,.tv_usec=0};
    if(ioctl(fd,VIDIOC_S_DQBUF_TIMEOUT,&timeout)!=0){err=ESP_FAIL;goto done;}
    int type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if(ioctl(fd,VIDIOC_STREAMON,&type)!=0){err=ESP_FAIL;goto done;}
    streaming=1;
    ESP_LOGI(TAG,"CAM_CAPTURING warmup_frames=5 timeout_ms=10000");
    int good=0,dq_ok=0,dq_fail=0,last_errno=0,bad=0;
    unsigned last_used=0,last_index=0;
    int64_t deadline=esp_timer_get_time()+10000000;
    while(esp_timer_get_time()<deadline && !cancelled) {
        struct v4l2_buffer b={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};
        if(ioctl(fd,VIDIOC_DQBUF,&b)!=0) {++dq_fail;last_errno=errno;continue;}
        ++dq_ok;last_used=b.bytesused;last_index=b.index;
        int valid=b.index<2 && b.bytesused==width*height*2 && b.bytesused<=sizes[b.index];
        if(!valid)++bad;
        if(dq_ok<=3) ESP_LOGI(TAG,"FRAME_DIAG received=%d index=%u used=%u expected=%u valid=%d",dq_ok,(unsigned)b.index,(unsigned)b.bytesused,(unsigned)(width*height*2),valid);
        if(valid && ++good>=5) {
            const uint8_t *src=buffers[b.index];
            memcpy(raw,src,width*height*2);
            make_thumb(src,thumb);
        }
        if(ioctl(fd,VIDIOC_QBUF,&b)!=0){err=ESP_FAIL;goto done;}
        if(valid && good>=5) break;
    }
    if(cancelled){err=ESP_ERR_INVALID_STATE;goto done;}
    ESP_LOGI(TAG,"FRAME_DIAG received=%d good=%d bad=%d dq_fail=%d errno=%d last_index=%u last_used=%u",dq_ok,good,bad,dq_fail,last_errno,last_index,last_used);
    if(good<5){err=ESP_ERR_TIMEOUT;goto done;}
    if(ioctl(fd,VIDIOC_STREAMOFF,&type)!=0){err=ESP_FAIL;goto done;}
    streaming=0;
    ++sequence;
    printf("LIVE_START {\"id\":%u,\"rotation\":%d,\"capture_ms\":%lld}\r\n",sequence,rotation,(long long)(esp_timer_get_time()/1000));
    uint32_t n=38400,hash=fnv32(thumb,n);
    printf("\r\nCAM_BEGIN %lu 120 160 UYVY %08lx\r\n",(unsigned long)n,(unsigned long)hash);
    send_hex(thumb,n);
    if(cancelled){printf("CAM_ABORT cancelled\r\n");err=ESP_ERR_INVALID_STATE;}
    else {printf("CAM_END %lu %08lx\r\n",(unsigned long)n,(unsigned long)hash);err=ESP_OK;}
done:
    if(fd>=0) {
        if(streaming){int t=V4L2_BUF_TYPE_VIDEO_CAPTURE;ioctl(fd,VIDIOC_STREAMOFF,&t);}
        for(int i=0;i<2;i++)if(buffers[i])munmap(buffers[i],sizes[i]);
        close(fd);
    }
    if(thumb)free(thumb);
    if(err==ESP_OK && raw && !cancelled) {
        if(job==3) err=detect_engine_run(raw,width,height,fourcc,rotation,sequence,&cancelled);
        else err=pose_engine_run(raw,width,height,fourcc,rotation,sequence,&cancelled);
    }
    if(raw)free(raw);
    return err;
}

static void worker(void *arg)
{
    (void)arg;
    for(;;) {
        int job;xQueueReceive(jobs,&job,portMAX_DELAY);
        esp_err_t err=job==4?stream():operate(job);
        last_error=err;
        if(err!=ESP_OK)ESP_LOGE(TAG,"CAM_ERROR rc=%d reason=%s check=3V3_GND_SDA21_SCL47_VSYNC4_PCLK9_D0_8_PWDN41",err,esp_err_to_name(err));
        ESP_LOGI(TAG,"CAM_DONE result=%s streaming=OFF",err==ESP_OK?"OK":"ERROR");
        portENTER_CRITICAL(&mux);busy=0;portEXIT_CRITICAL(&mux);
    }
}

static void command(char *out,int len,int argc,char **argv)
{
    (void)out;(void)len;
    if(argc==2 && !strncmp(argv[1],"rotate",6)) {
        int value=-1;
        if(!strcmp(argv[1],"rotate0"))value=0;
        if(!strcmp(argv[1],"rotate90"))value=90;
        if(!strcmp(argv[1],"rotate180"))value=180;
        if(!strcmp(argv[1],"rotate270"))value=270;
        if(value>=0 && !busy){rotation=value;ESP_LOGI(TAG,"LIVE_ROTATION %d",value);}
        else {ESP_LOGW(TAG,"CAM_ERROR rotation_or_busy");}
        return;
    }
    if(argc==2 && !strcmp(argv[1],"status")){status();return;}
    if(argc==2 && (!strcmp(argv[1],"stop") || !strcmp(argv[1],"stream_stop"))){cancelled=1;ESP_LOGI(TAG,"CAM_STOP requested");return;}
    if(argc==3 && !strcmp(argv[1],"preview")) {
        char *end=NULL;long n=strtol(argv[2],&end,10);
        if(end && !*end && n>=0 && n<=1000){preview_every=(int)n;ESP_LOGI(TAG,"LIVE_PREVIEW every=%d",preview_every);}
        else ESP_LOGW(TAG,"CAM_ERROR preview_range");
        return;
    }
    int job=argc!=2?0:!strcmp(argv[1],"probe")?1:!strcmp(argv[1],"capture")?2:!strcmp(argv[1],"detect")?3:!strcmp(argv[1],"stream_start")?4:0;
    if(!job){ESP_LOGW(TAG,"CAM_ERROR invalid_command");return;}
    portENTER_CRITICAL(&mux);int reject=busy;if(!reject){busy=1;cancelled=0;}portEXIT_CRITICAL(&mux);
    if(reject){ESP_LOGW(TAG,"CAM_ERROR busy");return;}
    if(xQueueSend(jobs,&job,0)!=pdTRUE){busy=0;ESP_LOGE(TAG,"CAM_ERROR queue_full");}
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    // Reject narrow VSYNC/CS pulses before they reach the SPI peripheral.
    // Keep frame/line-header and payload-length validation unchanged.
    const gpio_pin_glitch_filter_config_t filter_config = {.gpio_num = 4};
    esp_err_t filter_err = gpio_new_pin_glitch_filter(&filter_config, &vsync_filter);
    if (filter_err == ESP_OK) filter_err = gpio_glitch_filter_enable(vsync_filter);
    if (filter_err != ESP_OK) {
        ESP_LOGE(TAG, "LIVE_ERROR vsync_filter rc=%d", filter_err);
        if (vsync_filter) gpio_del_glitch_filter(vsync_filter);
        return;
    }
    ESP_LOGI(TAG, "VSYNC_FILTER gpio=4 enabled=1 window=fixed_two_iomux_cycles");
    if(pose_engine_init()!=ESP_OK) {ESP_LOGE(TAG,"LIVE_ERROR model_init");return;}
    if(detect_engine_init()!=ESP_OK) {ESP_LOGE(TAG,"LIVE_ERROR detect_model_init");return;}
    preview_data=heap_caps_malloc(THUMB_BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!preview_data || xTaskCreate(preview_task,"preview",4096,NULL,3,&preview_task_handle)!=pdPASS) {
        ESP_LOGE(TAG,"CAM_ERROR preview_init"); return;
    }
    jobs=xQueueCreate(1,sizeof(int));
    if(!jobs || xTaskCreate(worker,"camera_test",8192,NULL,6,NULL)!=pdPASS) {
        ESP_LOGE(TAG,"CAM_ERROR task_init"); return;
    }
    ESP_LOGI(TAG,"LIVE_READY model=YOLO11N_S3_V1 baud=%d capture=OFF no_motor=1 no_audio=1 no_network=1 psram=%u", CONFIG_ESP_CONSOLE_UART_BAUDRATE,(unsigned)esp_psram_get_size());
    char line[80]; unsigned used=0; int overflow=0;
    for(;;) {
        int c=getchar();
        if(c==EOF) {clearerr(stdin);vTaskDelay(pdMS_TO_TICKS(10));continue;}
        if(c=='\r' || c=='\n') {
            line[used]=0;
            if(!overflow && used) {
                char *save=NULL; char *argv[3]; int argc=0;
                for(char *p=strtok_r(line," ", &save);p && argc<3;p=strtok_r(NULL," ",&save)) argv[argc++]=p;
                if(argc>=2 && !strcmp(argv[0],"cam_test")) command(NULL,0,argc,argv);
                else ESP_LOGW(TAG,"CAM_ERROR invalid_command");
            }
            used=0;overflow=0;
        } else if(used<sizeof(line)-1) line[used++]=(char)c;
        else overflow=1;
    }
}
