// Uses the supplied Espressif ESP-DL 3.3.14 / COCO Pose 0.4.1 runtime and S3 V1 model.
#include "pose_engine.h"
#include "coco_pose.hpp"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <linux/videodev2.h>
#include <cstdio>
#include <string>
#include <algorithm>

static COCOPose *model;
static uint8_t clip(int a){return (uint8_t)std::max(0,std::min(255,a));}

extern "C" esp_err_t pose_engine_init(void)
{
    int64_t start=esp_timer_get_time();
    model=new COCOPose(COCOPose::YOLO11N_POSE_S8_V1,false);
    ESP_LOGI("LIVE_POSE","model_loaded_ms=%.1f psram_free=%u",(esp_timer_get_time()-start)/1000.0,
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    return model?ESP_OK:ESP_ERR_NO_MEM;
}

extern "C" esp_err_t pose_engine_run(const uint8_t *raw,int w,int h,uint32_t fourcc,int rotation,unsigned sequence,volatile int *cancelled)
{
    if(!model || !raw || (fourcc!=V4L2_PIX_FMT_UYVY && fourcc!=V4L2_PIX_FMT_YUYV))return ESP_ERR_INVALID_ARG;
    int rw=(rotation==90||rotation==270)?h:w;
    int rh=(rotation==90||rotation==270)?w:h;
    uint8_t *rgb=(uint8_t*)heap_caps_malloc(w*h*3,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!rgb)return ESP_ERR_NO_MEM;
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
        uint8_t *q=rgb+(ty*rw+tx)*3;
        q[0]=clip((298*c+409*e+128)>>8);
        q[1]=clip((298*c-100*d-208*e+128)>>8);
        q[2]=clip((298*c+516*d+128)>>8);
    }
    dl::image::img_t img={.data=rgb,.width=(uint16_t)rw,.height=(uint16_t)rh,.pix_type=dl::image::DL_IMAGE_PIX_TYPE_RGB888};
    int64_t start=esp_timer_get_time();
    auto &results=model->run(img);
    double elapsed=(esp_timer_get_time()-start)/1000.0;
    heap_caps_free(rgb);
    if(*cancelled){printf("POSE_CANCELLED id=%u inference_finished=1\r\n",sequence);return ESP_OK;}
    char header[256];
    snprintf(header,sizeof(header),"{\"id\":%u,\"width\":%d,\"height\":%d,\"rotation\":%d,\"inference_ms\":%.1f,\"psram_free\":%u,\"people\":[",sequence,rw,rh,rotation,elapsed,
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    std::string out=header;
    unsigned count=0;
    for(const auto &r:results) {
        if(count>=5)break;
        if(count++)out+=",";
        char person[192];
        snprintf(person,sizeof(person),"{\"score\":%.4f,\"box\":[%d,%d,%d,%d],\"keypoints\":[",r.score,r.box[0],r.box[1],r.box[2],r.box[3]);
        out+=person;
        for(int i=0;i<17;i++) {
            if(i)out+=",";
            if(r.keypoint.size()<unsigned(i*2+2) || (r.keypoint[i*2]==0 && r.keypoint[i*2+1]==0))out+="null";
            else {char point[40];snprintf(point,sizeof(point),"[%d,%d]",r.keypoint[i*2],r.keypoint[i*2+1]);out+=point;}
        }
        out+="]}";
    }
    out+="]}";
    printf("POSE_RESULT %s\r\n",out.c_str());
    return ESP_OK;
}
