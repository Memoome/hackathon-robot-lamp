#include "camera_test.h"
#if defined(CONFIG_OFFLINE_AUDIO_TEST) && CONFIG_OFFLINE_AUDIO_TEST
#include "qm.h"
#include "qm_cli.h"
#include "driver/gpio.h"
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
static uint32_t width,height,fourcc;

static void status(void)
{
    QM_LOGI(TAG,"CAM_STATUS version=1 busy=%d detected=%d width=%lu height=%lu pclk=9 sda=21 scl=47 cs=4 data=8 pwdn=41 error=%d",busy,detected,(unsigned long)width,(unsigned long)height,last_error);
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

static esp_err_t operate(int capture)
{
    int fd=-1,streaming=0;
    uint8_t *buffers[2]={0},*thumb=NULL;
    size_t sizes[2]={0};
    esp_err_t err=setup_video();
    if(err!=ESP_OK) return err;
    fd=open(ESP_VIDEO_SPI_DEVICE_NAME,O_RDWR);
    if(fd<0) return ESP_FAIL;
    struct v4l2_format fmt={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE};
    if(ioctl(fd,VIDIOC_G_FMT,&fmt)!=0){err=ESP_FAIL;goto done;}
    width=fmt.fmt.pix.width;height=fmt.fmt.pix.height;fourcc=fmt.fmt.pix.pixelformat;
    detected=1;
    QM_LOGI(TAG,"CAM_PROBE_OK sensor=BF3901 width=%lu height=%lu fourcc=%08lx pclk=9 xclk=ONBOARD",(unsigned long)width,(unsigned long)height,(unsigned long)fourcc);
    if(!capture) {err=ESP_OK;goto done;}
    if((fourcc!=V4L2_PIX_FMT_UYVY && fourcc!=V4L2_PIX_FMT_YUYV) || width!=240 || height!=320) {err=ESP_ERR_NOT_SUPPORTED;goto done;}
    thumb=heap_caps_malloc(120*160*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!thumb){err=ESP_ERR_NO_MEM;goto done;}
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
    QM_LOGI(TAG,"CAM_CAPTURING warmup_frames=5 timeout_ms=10000");
    int good=0;int64_t deadline=esp_timer_get_time()+10000000;
    while(esp_timer_get_time()<deadline && !cancelled) {
        struct v4l2_buffer b={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP};
        if(ioctl(fd,VIDIOC_DQBUF,&b)!=0) continue;
        int valid=b.index<2 && b.bytesused==width*height*2 && b.bytesused<=sizes[b.index];
        if(valid && ++good>=5) {
            const uint8_t *src=buffers[b.index];
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
        if(ioctl(fd,VIDIOC_QBUF,&b)!=0){err=ESP_FAIL;goto done;}
        if(valid && good>=5) break;
    }
    if(cancelled){err=ESP_ERR_INVALID_STATE;goto done;}
    if(good<5){err=ESP_ERR_TIMEOUT;goto done;}
    if(ioctl(fd,VIDIOC_STREAMOFF,&type)!=0){err=ESP_FAIL;goto done;}
    streaming=0;
    uint32_t n=38400,hash=fnv32(thumb,n);
    qm_cli_printf("\r\nCAM_BEGIN %lu 120 160 UYVY %08lx\r\n",(unsigned long)n,(unsigned long)hash);
    const char hexchars[]="0123456789abcdef";
    for(uint32_t off=0;off<n && !cancelled;) {
        char hex[193];uint32_t count=n-off;if(count>96)count=96;
        for(uint32_t i=0;i<count;i++){uint8_t c=thumb[off+i];hex[2*i]=hexchars[c>>4];hex[2*i+1]=hexchars[c&15];}
        hex[count*2]=0;qm_cli_printf("CAM_DATA %lu %s\r\n",(unsigned long)off,hex);
        off+=count;if(!(off%3072u))vTaskDelay(1);
    }
    if(cancelled){qm_cli_printf("CAM_ABORT cancelled\r\n");err=ESP_ERR_INVALID_STATE;}
    else {qm_cli_printf("CAM_END %lu %08lx\r\n",(unsigned long)n,(unsigned long)hash);err=ESP_OK;}
done:
    if(fd>=0) {
        if(streaming){int t=V4L2_BUF_TYPE_VIDEO_CAPTURE;ioctl(fd,VIDIOC_STREAMOFF,&t);}
        for(int i=0;i<2;i++)if(buffers[i])munmap(buffers[i],sizes[i]);
        close(fd);
    }
    if(thumb)free(thumb);
    return err;
}

static void worker(void *arg)
{
    (void)arg;
    for(;;) {
        int job;xQueueReceive(jobs,&job,portMAX_DELAY);
        esp_err_t err=operate(job==2);
        last_error=err;
        if(err!=ESP_OK)QM_LOGE(TAG,"CAM_ERROR rc=%d reason=%s check=3V3_GND_SDA21_SCL47_VSYNC4_PCLK9_D0_8_PWDN41",err,esp_err_to_name(err));
        QM_LOGI(TAG,"CAM_DONE result=%s streaming=OFF",err==ESP_OK?"OK":"ERROR");
        portENTER_CRITICAL(&mux);busy=0;portEXIT_CRITICAL(&mux);
    }
}

static void command(char *out,int len,int argc,char **argv)
{
    (void)out;(void)len;
    if(argc==2 && !strcmp(argv[1],"status")){status();return;}
    if(argc==2 && !strcmp(argv[1],"stop")){cancelled=1;QM_LOGI(TAG,"CAM_STOP requested");return;}
    int job=argc==2 && !strcmp(argv[1],"probe")?1:argc==2 && !strcmp(argv[1],"capture")?2:0;
    if(!job){QM_LOGW(TAG,"CAM_ERROR invalid_command");return;}
    portENTER_CRITICAL(&mux);int reject=busy;if(!reject){busy=1;cancelled=0;}portEXIT_CRITICAL(&mux);
    if(reject){QM_LOGW(TAG,"CAM_ERROR busy");return;}
    if(xQueueSend(jobs,&job,0)!=pdTRUE){busy=0;QM_LOGE(TAG,"CAM_ERROR queue_full");}
}
static const struct qm_cli_command cli={"cam_test","Camera status/probe/capture/stop; PCLK GPIO9",command};
esp_err_t camera_test_init(void)
{
    jobs=xQueueCreate(1,sizeof(int));if(!jobs)return ESP_ERR_NO_MEM;
    if(qm_cli_register_command(&cli)!=QM_EOK)return ESP_FAIL;
    if(xTaskCreate(worker,"camera_test",8192,NULL,6,NULL)!=pdPASS)return ESP_ERR_NO_MEM;
    QM_LOGI(TAG,"CAM_READY version=1 pclk=9 capture=OFF xclk=ONBOARD");
    return ESP_OK;
}
#endif
