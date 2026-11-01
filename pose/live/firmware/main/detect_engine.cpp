// Uses the Espressif ESP-DL 3.3.14 / PedestrianDetect PICO_S8_V1 runtime and model.
// Box + score only, no keypoints.
#include "detect_engine.h"
#include "pedestrian_detect.hpp"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <linux/videodev2.h>
#include <cstdio>
#include <string>
#include <algorithm>

static PedestrianDetect *model;
static uint8_t *rgb;
static uint8_t clip(int a){return (uint8_t)std::max(0,std::min(255,a));}

extern "C" esp_err_t detect_engine_init(void)
{
    int64_t start=esp_timer_get_time();
    model=new PedestrianDetect(PedestrianDetect::PICO_S8_V1,false);
    rgb=(uint8_t*)heap_caps_malloc(240*320*3,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    ESP_LOGI("LIVE_DETECT","model_loaded_ms=%.1f psram_free=%u",(esp_timer_get_time()-start)/1000.0,
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    return model && rgb?ESP_OK:ESP_ERR_NO_MEM;
}

static esp_err_t infer(const uint8_t *raw,int w,int h,uint32_t fourcc,int rotation,int *rw,int *rh,
                       double *prep_ms,double *infer_ms,std::string &people,presence_box_t *boxes=nullptr,int *box_count=nullptr)
{
    if(!model || !rgb || !raw || w*h>240*320 || (fourcc!=V4L2_PIX_FMT_UYVY && fourcc!=V4L2_PIX_FMT_YUYV))return ESP_ERR_INVALID_ARG;
    *rw=(rotation==90||rotation==270)?h:w;
    *rh=(rotation==90||rotation==270)?w:h;
    int64_t start=esp_timer_get_time();
    for(int y=0;y<h;y++)for(int x=0;x<w;x++) {
        const uint8_t *p=raw+(y*w+(x&~1))*2;
        int u,v,l;
        if(fourcc==V4L2_PIX_FMT_UYVY){u=p[0];v=p[2];l=p[(x&1)?3:1];}
        else {u=p[1];v=p[3];l=p[(x&1)?2:0];}
        int c=std::max(0,l-16),d=u-128,e=v-128;
        int tx=x,ty=y;
        if(rotation==90){tx=h-1-y;ty=x;}
        else if(rotation==180){tx=w-1-x;ty=h-1-y;}
        else if(rotation==270){tx=y;ty=w-1-x;}
        uint8_t *q=rgb+(ty*(*rw)+tx)*3;
        q[0]=clip((298*c+409*e+128)>>8);
        q[1]=clip((298*c-100*d-208*e+128)>>8);
        q[2]=clip((298*c+516*d+128)>>8);
    }
    int64_t mid=esp_timer_get_time();
    dl::image::img_t img={.data=rgb,.width=(uint16_t)*rw,.height=(uint16_t)*rh,.pix_type=dl::image::DL_IMAGE_PIX_TYPE_RGB888};
    auto &results=model->run(img);
    int64_t end=esp_timer_get_time();
    *prep_ms=(mid-start)/1000.0;
    *infer_ms=(end-mid)/1000.0;
    people.clear();
    unsigned count=0;
    for(const auto &r:results) {
        if(count>=5)break;
        if(count++)people+=",";
        int cx=(r.box[0]+r.box[2])/2,cy=(r.box[1]+r.box[3])/2;
        char person[160];
        snprintf(person,sizeof(person),"{\"score\":%.4f,\"box\":[%d,%d,%d,%d],\"center\":[%d,%d]}",r.score,r.box[0],r.box[1],r.box[2],r.box[3],cx,cy);
        people+=person;
        if(boxes){boxes[count-1].score=r.score;for(int i=0;i<4;i++)boxes[count-1].box[i]=r.box[i];}
    }
    if(box_count)*box_count=(int)count;
    return ESP_OK;
}

extern "C" esp_err_t detect_engine_run(const uint8_t *raw,int w,int h,uint32_t fourcc,int rotation,unsigned sequence,volatile int *cancelled)
{
    int rw,rh;double prep,elapsed;std::string people;
    esp_err_t err=infer(raw,w,h,fourcc,rotation,&rw,&rh,&prep,&elapsed,people);
    if(err!=ESP_OK)return err;
    if(*cancelled){printf("DETECT_CANCELLED id=%u inference_finished=1\r\n",sequence);return ESP_OK;}
    printf("DETECT_RESULT {\"id\":%u,\"width\":%d,\"height\":%d,\"rotation\":%d,\"inference_ms\":%.1f,\"psram_free\":%u,\"people\":[%s]}\r\n",
           sequence,rw,rh,rotation,elapsed,(unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),people.c_str());
    return ESP_OK;
}

extern "C" esp_err_t detect_engine_stream(const uint8_t *raw,int w,int h,uint32_t fourcc,int rotation,unsigned sequence,int64_t t_ms,double cycle_ms,
                                          presence_box_t *boxes,int *box_count,int *out_w,int *out_h)
{
    int rw,rh;double prep,elapsed;std::string people;
    esp_err_t err=infer(raw,w,h,fourcc,rotation,&rw,&rh,&prep,&elapsed,people,boxes,box_count);
    if(err!=ESP_OK)return err;
    *out_w=rw;*out_h=rh;
    char header[192];
    snprintf(header,sizeof(header),"DET {\"seq\":%u,\"t_ms\":%lld,\"width\":%d,\"height\":%d,\"rotation\":%d,\"prep_ms\":%.1f,\"infer_ms\":%.1f,\"cycle_ms\":%.1f,\"people\":[",
             sequence,(long long)t_ms,rw,rh,rotation,prep,elapsed,cycle_ms);
    std::string line=std::string(header)+people+"]}\r\n";
    // One write per line: the preview task prints on the same UART concurrently.
    fwrite(line.data(),1,line.size(),stdout);
    return ESP_OK;
}
