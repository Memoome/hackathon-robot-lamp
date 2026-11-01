#pragma once
// Board-side presence states 1-4 (docs/VISION-POSE-ARCHITECTURE.md 6.1), boxes only.
// Plain C with no ESP-IDF dependency so it can be unit-tested on the host.
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define PRESENCE_MAX_BOXES 5
#define PRESENCE_CALIB_FRAMES 5
// Auto baseline: up to ~25 s of frames at ~6/s.
#define PRESENCE_AUTO_SAMPLES 160

typedef struct {float score;int box[4];} presence_box_t;

typedef enum {LEVEL_UNKNOWN,LEVEL_OK,LEVEL_WATCH,LEVEL_ALERT} presence_level_t;
typedef enum {CALIB_NONE,CALIB_AUTO,CALIB_MANUAL} presence_calib_source_t;

typedef struct {
    // Tunables (provisional, section 6.1).
    int away_ms,back_ms,rest_ms,close_alert_ms,stand_ms,auto_calib_ms;
    int sit_watch_s,sit_alert_s;
    float close_ratio,stand_rise;
    // Main-box tracking.
    int has_main,main[4],stable_frames;
    int64_t last_t,last_seen,present_since;
    // Debounced states.
    int away,standing;
    presence_level_t sedentary,too_close;
    double sit_ms;
    int64_t close_since,stand_since;
    // Baseline from cam_test calib.
    int calibrated,calibrating,calib_n;
    int64_t calib_deadline;
    float base_area,base_top,base_h,calib_sum[3];
    presence_calib_source_t calib_source;
    // Auto baseline: the main box stayed still and well placed since auto_since.
    int64_t auto_since;
    int auto_n;
    float auto_samples[3][PRESENCE_AUTO_SAMPLES];
    // Why auto calibration is not progressing (NULL when calibrated or collecting).
    const char *calib_hint;
    // Last frame metrics, NAN when unavailable.
    float area_ratio,rise;
    const char *event;
} presence_t;

void presence_init(presence_t *p,int64_t t_ms);
// Starts a manual baseline over the next PRESENCE_CALIB_FRAMES frames with a person (gives up after 3 s).
// Without it the baseline is taken automatically once one person sits still and well placed for
// auto_calib_ms; a rest of rest_ms (away) discards either kind.
void presence_calibrate(presence_t *p,int64_t t_ms);
// Returns a bitmask: 1 = reportable state changed, 2 = calibration finished, 4 = calibration failed.
int presence_update(presence_t *p,int64_t t_ms,const presence_box_t *boxes,int n,int frame_w,int frame_h);
// Main box present and its centre has moved less than 5% of the frame for 3 frames.
int presence_stable(const presence_t *p);
int presence_json(const presence_t *p,unsigned seq,int64_t t_ms,char *buf,size_t size);
const char *presence_level_name(presence_level_t level);

#ifdef __cplusplus
}
#endif
