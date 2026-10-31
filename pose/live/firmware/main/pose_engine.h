#pragma once
#include <stdint.h>
#include "esp_err.h"
#ifdef __cplusplus
extern "C" {
#endif
esp_err_t pose_engine_init(void);
esp_err_t pose_engine_run(const uint8_t *raw,int w,int h,uint32_t fourcc,int rotation,unsigned sequence,volatile int *cancelled);
#ifdef __cplusplus
}
#endif
