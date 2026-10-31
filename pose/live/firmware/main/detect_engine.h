#pragma once
#include <stdint.h>
#include "esp_err.h"
#include "presence.h"
#ifdef __cplusplus
extern "C" {
#endif
esp_err_t detect_engine_init(void);
esp_err_t detect_engine_run(const uint8_t *raw,int w,int h,uint32_t fourcc,int rotation,unsigned sequence,volatile int *cancelled);
// Prints one DET line and returns up to PRESENCE_MAX_BOXES boxes in the rotated out_w x out_h frame.
esp_err_t detect_engine_stream(const uint8_t *raw,int w,int h,uint32_t fourcc,int rotation,unsigned sequence,int64_t t_ms,double cycle_ms,
                               presence_box_t *boxes,int *box_count,int *out_w,int *out_h);
#ifdef __cplusplus
}
#endif
