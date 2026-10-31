#pragma once
#include <stdint.h>
#include "esp_err.h"
#ifdef __cplusplus
extern "C" {
#endif
esp_err_t detect_engine_init(void);
esp_err_t detect_engine_run(const uint8_t *raw,int w,int h,uint32_t fourcc,int rotation,unsigned sequence,volatile int *cancelled);
esp_err_t detect_engine_stream(const uint8_t *raw,int w,int h,uint32_t fourcc,int rotation,unsigned sequence,int64_t t_ms,double cycle_ms);
#ifdef __cplusplus
}
#endif
