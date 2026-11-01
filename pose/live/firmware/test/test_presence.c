// Host-side test for main/presence.c: cc -I../main test_presence.c ../main/presence.c -lm
// Prints sample PRESENCE JSON lines for host/test_presence_fw.py to parse.
#include "presence.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static presence_t p;
static int64_t t;
static presence_box_t seated={0.8f,{110,60,210,240}},moved={0.8f,{140,60,240,240}};

// Feeds frames every 166 ms (about 6/s) for `ms`, returns the OR of update results.
static int run(int64_t ms,const presence_box_t *box)
{
    int r=0;
    for(int64_t end=t+ms;t<end;){t+=166;r|=presence_update(&p,t,box,box?1:0,320,240);}
    return r;
}

static void print(void)
{
    char buf[400];
    int n=presence_json(&p,42,t,buf,sizeof(buf));
    assert(n>0 && n<(int)sizeof(buf));
    printf("%s\n",buf);
}

int main(void)
{
    presence_init(&p,0);
    print();
    // 1 away after 10 s without anyone, back after 3 s of presence.
    run(9800,NULL);assert(!p.away);
    run(400,NULL);assert(p.away);
    run(2800,&seated);assert(p.away);
    run(400,&seated);assert(!p.away);
    // A one-frame miss does not restart the back timer or trigger away.
    run(500,&seated);
    run(166,NULL);assert(!p.away);

    // 2 sedentary: limits shortened as with cam_test sit_limits.
    presence_init(&p,t);p.sit_watch_s=5;p.sit_alert_s=8;
    run(5200,&seated);assert(p.sedentary==LEVEL_WATCH);
    run(3000,&seated);assert(p.sedentary==LEVEL_ALERT);
    // A 30 s break (away, but < 2 min) keeps the count.
    run(30000,NULL);assert(p.away && p.sit_ms>8000);
    run(3500,&seated);assert(!p.away && p.sedentary==LEVEL_ALERT);
    // A 2 min break clears it.
    run(121000,NULL);assert(p.sit_ms==0 && p.sedentary==LEVEL_OK);

    // 3/4 need the baseline.
    presence_init(&p,t);
    assert(p.too_close==LEVEL_UNKNOWN);
    presence_calibrate(&p,t);
    int r=run(1000,&seated);
    assert(r&2 && p.calibrated && fabsf(p.base_area-100*180)<1 && p.too_close==LEVEL_OK);
    print();
    // Leaning in: box 1.6x area, top edge not raised.
    presence_box_t close={0.8f,{90,60,220,282}};
    run(5000,&close);assert(p.too_close==LEVEL_WATCH && !p.standing);
    run(5200,&close);assert(p.too_close==LEVEL_ALERT);
    print();
    run(500,&seated);assert(p.too_close==LEVEL_OK);
    // Standing: top edge rises by 30% of the baseline height for 2 s; not counted as too close.
    presence_box_t standing={0.8f,{100,6,220,240}};
    run(1800,&standing);assert(!p.standing);
    run(400,&standing);assert(p.standing && p.too_close==LEVEL_OK);
    print();
    run(500,&seated);assert(!p.standing);

    assert(p.calib_source==CALIB_MANUAL);

    // Auto baseline: one person still and well placed for 20 s.
    presence_init(&p,t);
    run(10000,&seated);
    run(166,NULL);                      // a single missed detection keeps collecting
    run(9000,&seated);
    assert(!p.calibrated && p.calib_hint && !strcmp(p.calib_hint,"collecting"));
    r=run(1200,&seated);
    assert(r&2 && p.calibrated && p.calib_source==CALIB_AUTO && fabsf(p.base_area-100*180)<1 && p.calib_hint==NULL);
    print();
    // No auto baseline when the box leaves no room to detect leaning in or standing up.
    presence_box_t huge={0.9f,{10,20,300,239}},top={0.9f,{110,2,210,200}},edge={0.9f,{0,40,120,239}};
    presence_init(&p,t);run(30000,&huge);assert(!p.calibrated && !strcmp(p.calib_hint,"too_large"));
    presence_init(&p,t);run(30000,&top);assert(!p.calibrated && !strcmp(p.calib_hint,"touching_top"));
    presence_init(&p,t);run(30000,&edge);assert(!p.calibrated && !strcmp(p.calib_hint,"at_edge"));
    // Moving around restarts the 20 s.
    presence_init(&p,t);
    for(int i=0;i<60;i++)run(500,i%2?&seated:&moved);
    assert(!p.calibrated && t-p.auto_since<1000);
    run(166,&moved);assert(!strcmp(p.calib_hint,"moving"));
    // A 2 min absence discards the baseline; the next person gets a new one.
    presence_init(&p,t);
    run(20500,&seated);assert(p.calibrated);
    run(60000,NULL);assert(p.calibrated);          // short break keeps it
    run(3500,&seated);
    run(121000,NULL);assert(!p.calibrated && p.calib_source==CALIB_NONE && p.too_close==LEVEL_UNKNOWN);
    run(23500,&huge);assert(!p.calibrated);        // too large to calibrate on
    run(20500,&seated);assert(p.calibrated && p.calib_source==CALIB_AUTO);

    // Calibration gives up after 3 s with nobody in view.
    presence_calibrate(&p,t);
    r=run(3400,NULL);assert(r&4 && !p.calibrating);

    // Stability: 3 frames with the centre moving less than 16 px.
    presence_init(&p,t);
    run(166,&seated);assert(!presence_stable(&p));
    run(332,&seated);assert(presence_stable(&p));
    run(166,&moved);assert(!presence_stable(&p));

    // Main box follows the tracked person even if a second one scores higher.
    presence_box_t two[2]={{0.9f,{0,0,60,120}},{0.5f,{112,62,212,242}}};
    t+=166;presence_update(&p,t,two,2,320,240);
    assert(p.main[0]==112);
    print();
    fprintf(stderr,"presence: all assertions passed\n");
    return 0;
}
