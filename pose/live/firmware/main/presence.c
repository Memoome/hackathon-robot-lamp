#include "presence.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// A detection gap longer than this restarts the "back" timer and expires too_close/standing.
#define GAP_MS 1000

const char *presence_level_name(presence_level_t level)
{
    static const char *names[]={"unknown","ok","watch","alert"};
    return names[level];
}

void presence_init(presence_t *p,int64_t t_ms)
{
    memset(p,0,sizeof(*p));
    p->away_ms=10000;p->back_ms=3000;p->rest_ms=120000;p->close_alert_ms=10000;p->stand_ms=2000;p->auto_calib_ms=20000;
    p->sit_watch_s=40*60;p->sit_alert_s=45*60;
    p->close_ratio=1.5f;p->stand_rise=0.2f;
    p->last_t=p->last_seen=t_ms;p->present_since=p->close_since=p->stand_since=p->auto_since=-1;
    p->sedentary=LEVEL_OK;p->too_close=LEVEL_UNKNOWN;
    p->area_ratio=p->rise=NAN;
}

void presence_calibrate(presence_t *p,int64_t t_ms)
{
    p->calibrating=1;p->calib_n=0;p->calib_deadline=t_ms+3000;
    memset(p->calib_sum,0,sizeof(p->calib_sum));
}

static int cmp_float(const void *a,const void *b)
{
    float x=*(const float*)a,y=*(const float*)b;
    return (x>y)-(x<y);
}

static float median(float *v,int n)
{
    qsort(v,n,sizeof(*v),cmp_float);
    return n%2?v[n/2]:(v[n/2-1]+v[n/2])/2;
}

static void set_baseline(presence_t *p,float area,float top,float h,presence_calib_source_t source)
{
    p->base_area=area;p->base_top=top;p->base_h=h;
    p->calibrated=1;p->calib_source=source;p->close_since=p->stand_since=-1;p->standing=0;
    p->auto_since=-1;p->auto_n=0;
}

// A baseline must leave room to detect leaning in (box grows) and standing up (top edge rises).
static const char *placement_problem(const int *b,int frame_w,int frame_h)
{
    float frac=(float)(b[2]-b[0])*(b[3]-b[1])/((float)frame_w*frame_h);
    if(frac>0.6f)return "too_large";
    if(frac<0.1f)return "too_small";
    if(b[1]<8)return "touching_top";
    if(b[0]<=2 || b[2]>=frame_w-3)return "at_edge";
    return NULL;
}

static void auto_calibrate(presence_t *p,int64_t t_ms,const int *b,int moved,int64_t absent_ms,int frame_w,int frame_h,int *result)
{
    const char *hint=NULL;
    if(b)hint=placement_problem(b,frame_w,frame_h);
    else if(absent_ms>GAP_MS)hint="no_person";
    if(!hint && moved)hint="moving";
    if(hint){p->auto_since=-1;p->auto_n=0;p->calib_hint=hint;return;}
    if(p->auto_since<0){p->auto_since=t_ms;p->auto_n=0;}
    if(b && p->auto_n<PRESENCE_AUTO_SAMPLES) {
        p->auto_samples[0][p->auto_n]=(float)(b[2]-b[0])*(b[3]-b[1]);
        p->auto_samples[1][p->auto_n]=b[1];
        p->auto_samples[2][p->auto_n]=b[3]-b[1];
        ++p->auto_n;
    }
    p->calib_hint="collecting";
    // Medians ignore the odd jumpy box; 30 samples is about 5 s of actual detections.
    if(t_ms-p->auto_since>=p->auto_calib_ms && p->auto_n>=30) {
        int n=p->auto_n;
        set_baseline(p,median(p->auto_samples[0],n),median(p->auto_samples[1],n),median(p->auto_samples[2],n),CALIB_AUTO);
        p->calib_hint=NULL;
        *result|=2;
    }
}

static float iou(const int *a,const int *b)
{
    int w=(a[2]<b[2]?a[2]:b[2])-(a[0]>b[0]?a[0]:b[0]);
    int h=(a[3]<b[3]?a[3]:b[3])-(a[1]>b[1]?a[1]:b[1]);
    if(w<=0 || h<=0)return 0;
    float inter=(float)w*h,ua=(float)(a[2]-a[0])*(a[3]-a[1])+(float)(b[2]-b[0])*(b[3]-b[1])-inter;
    return ua>0?inter/ua:0;
}

// Keeps following the previous main box when it overlaps a detection; otherwise takes the highest score.
static int pick_main(const presence_t *p,const presence_box_t *boxes,int n)
{
    int best=-1;float best_iou=0.3f;
    if(p->has_main)for(int i=0;i<n;i++){float v=iou(p->main,boxes[i].box);if(v>best_iou){best_iou=v;best=i;}}
    if(best<0)for(int i=0;i<n;i++)if(best<0 || boxes[i].score>boxes[best].score)best=i;
    return best;
}

int presence_update(presence_t *p,int64_t t_ms,const presence_box_t *boxes,int n,int frame_w,int frame_h)
{
    int before[5]={p->away,p->standing,p->sedentary,p->too_close,p->calibrated};
    int result=0;
    int64_t dt=t_ms-p->last_t;
    if(dt<0)dt=0;
    if(dt>GAP_MS)dt=GAP_MS;
    p->last_t=t_ms;p->event=NULL;
    if(n>PRESENCE_MAX_BOXES)n=PRESENCE_MAX_BOXES;
    int m=pick_main(p,boxes,n);
    const int *b=m>=0?boxes[m].box:NULL;
    int moved=0;
    if(b) {
        float limit=0.05f*(frame_w>frame_h?frame_w:frame_h);
        float dx=(b[0]+b[2]-p->main[0]-p->main[2])/2.0f,dy=(b[1]+b[3]-p->main[1]-p->main[3])/2.0f;
        int near=dx*dx+dy*dy<limit*limit;
        p->stable_frames=p->has_main && near?p->stable_frames+1:1;
        // Compared with the last main box even across a short detection gap.
        moved=p->main[2]>p->main[0] && !near;
        memcpy(p->main,b,sizeof(p->main));p->has_main=1;
        if(p->present_since<0 || t_ms-p->last_seen>GAP_MS)p->present_since=t_ms;
        p->last_seen=t_ms;
    } else {p->has_main=0;p->stable_frames=0;}
    int64_t absent_ms=t_ms-p->last_seen;

    // 1 away / back
    if(!p->away && absent_ms>=p->away_ms){p->away=1;p->event="leave";}
    else if(p->away && b && t_ms-p->present_since>=p->back_ms){p->away=0;p->event="back";}

    // 2 sedentary: short absences keep counting; only a rest of rest_ms clears it.
    if(!p->away)p->sit_ms+=dt;
    else if(absent_ms>=p->rest_ms) {
        p->sit_ms=0;
        // Someone else may sit down next, or the seat may have moved.
        if(p->calibrated){p->calibrated=0;p->calib_source=CALIB_NONE;p->standing=0;}
    }
    int sit_s=(int)(p->sit_ms/1000);
    p->sedentary=sit_s>=p->sit_alert_s?LEVEL_ALERT:sit_s>=p->sit_watch_s?LEVEL_WATCH:LEVEL_OK;

    if(p->calibrating) {
        if(b) {
            p->calib_sum[0]+=(float)(b[2]-b[0])*(b[3]-b[1]);p->calib_sum[1]+=b[1];p->calib_sum[2]+=b[3]-b[1];
            if(++p->calib_n>=PRESENCE_CALIB_FRAMES) {
                set_baseline(p,p->calib_sum[0]/p->calib_n,p->calib_sum[1]/p->calib_n,p->calib_sum[2]/p->calib_n,CALIB_MANUAL);
                p->calibrating=0;
                result|=2;
            }
        }
        if(p->calibrating && t_ms>p->calib_deadline){p->calibrating=0;result|=4;}
    }
    if(!p->calibrated && !p->calibrating)auto_calibrate(p,t_ms,b,moved,absent_ms,frame_w,frame_h,&result);
    else p->calib_hint=NULL;

    // 3 too_close and 4 standing need the baseline.
    p->area_ratio=p->rise=NAN;
    if(!p->calibrated)p->too_close=LEVEL_UNKNOWN;
    else if(b) {
        float h=(float)(b[3]-b[1]);
        p->area_ratio=(float)(b[2]-b[0])*h/p->base_area;
        p->rise=(p->base_top-b[1])/p->base_h;
        int up=p->rise>p->stand_rise || (b[1]<=2 && h>=1.2f*p->base_h);
        if(up){if(p->stand_since<0)p->stand_since=t_ms;}
        else p->stand_since=-1;
        p->standing=p->stand_since>=0 && t_ms-p->stand_since>=p->stand_ms;
        // Standing up also enlarges the box; do not report it as leaning in.
        if(!up && p->area_ratio>=p->close_ratio) {
            if(p->close_since<0)p->close_since=t_ms;
            p->too_close=t_ms-p->close_since>=p->close_alert_ms?LEVEL_ALERT:LEVEL_WATCH;
        } else {p->close_since=-1;p->too_close=LEVEL_OK;}
    } else if(absent_ms>GAP_MS) {
        p->too_close=LEVEL_UNKNOWN;p->close_since=p->stand_since=-1;
        if(p->away)p->standing=0;
    }

    int after[5]={p->away,p->standing,p->sedentary,p->too_close,p->calibrated};
    if(memcmp(before,after,sizeof(before)))result|=1;
    return result;
}

int presence_stable(const presence_t *p)
{
    return p->has_main && p->stable_frames>=3;
}

static void metric(char *out,size_t size,float v)
{
    if(isnan(v))snprintf(out,size,"null");
    else snprintf(out,size,"%.3f",v);
}

int presence_json(const presence_t *p,unsigned seq,int64_t t_ms,char *buf,size_t size)
{
    static const char *sources[]={"null","\"auto\"","\"manual\""};
    char ratio[16],rise[16],main_box[40]="null",event[16]="null",hint[24]="null";
    metric(ratio,sizeof(ratio),p->area_ratio);metric(rise,sizeof(rise),p->rise);
    if(p->has_main)snprintf(main_box,sizeof(main_box),"[%d,%d,%d,%d]",p->main[0],p->main[1],p->main[2],p->main[3]);
    if(p->event)snprintf(event,sizeof(event),"\"%s\"",p->event);
    if(p->calib_hint)snprintf(hint,sizeof(hint),"\"%s\"",p->calib_hint);
    int calib_s=p->auto_since>=0?(int)((p->last_t-p->auto_since)/1000):0;
    return snprintf(buf,size,"{\"seq\":%u,\"t_ms\":%lld,\"present\":%s,\"stable\":%s,\"sit_s\":%d,"
        "\"states\":{\"away\":%s,\"sedentary\":\"%s\",\"too_close\":\"%s\",\"standing\":%s},"
        "\"calibrated\":%s,\"calib_source\":%s,\"calib_hint\":%s,\"calib_s\":%d,\"event\":%s,\"metrics\":{\"area_ratio\":%s,\"rise\":%s},\"main\":%s}",
        seq,(long long)t_ms,p->has_main?"true":"false",presence_stable(p)?"true":"false",(int)(p->sit_ms/1000),
        p->away?"true":"false",presence_level_name(p->sedentary),presence_level_name(p->too_close),p->standing?"true":"false",
        p->calibrated?"true":"false",sources[p->calib_source],hint,calib_s,event,ratio,rise,main_box);
}
