// Based on Espressif's MIT-licensed yolo11_pose image example.
// Isolated static-image benchmark: no camera, audio, Wi-Fi, credentials or servos.
#include "coco_pose.hpp"
#include "dl_image_jpeg.hpp"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

extern const uint8_t bus_jpg_start[] asm("_binary_bus_jpg_start");
extern const uint8_t bus_jpg_end[] asm("_binary_bus_jpg_end");
static const char *TAG = "POSE_BENCH";

static void memory(const char *stage)
{
    ESP_LOGI(TAG, "%s internal_free=%u psram_free=%u psram_largest=%u", stage,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));
}

extern "C" void app_main(void)
{
    ESP_LOGI(TAG, "STATIC_IMAGE_ONLY esp-dl=3.3.14 model=S3_V1 NO_MOTOR NO_AUDIO NO_NETWORK");
    memory("boot");
    if (!esp_psram_is_initialized() || esp_psram_get_size() < 8 * 1024 * 1024) {
        ESP_LOGE(TAG, "8MiB PSRAM not available; benchmark stopped");
        return;
    }
    int64_t start = esp_timer_get_time();
    // Load before peripheral startup. On an 8MiB board keep weights flash-mapped.
    COCOPose pose(COCOPose::YOLO11N_POSE_S8_V1, false);
    ESP_LOGI(TAG, "load_ms=%.1f", (esp_timer_get_time() - start) / 1000.0);
    memory("model_loaded");
    dl::image::jpeg_img_t jpeg = {.data = (void *)bus_jpg_start,
        .data_len = (size_t)(bus_jpg_end - bus_jpg_start)};
    auto img = dl::image::sw_decode_jpeg(jpeg, dl::image::DL_IMAGE_PIX_TYPE_RGB888);
    if (!img.data) {
        ESP_LOGE(TAG, "JPEG decode failed; benchmark stopped");
        return;
    }
    memory("image_decoded");
    for (int run = 1; run <= 3; ++run) {
        start = esp_timer_get_time();
        auto &results = pose.run(img);
        ESP_LOGI(TAG, "run=%d inference_ms=%.1f people=%u", run,
            (esp_timer_get_time() - start) / 1000.0, (unsigned)results.size());
        for (const auto &result : results) {
            ESP_LOGI(TAG, "person score=%.3f box=[%d,%d,%d,%d]", result.score,
                result.box[0], result.box[1], result.box[2], result.box[3]);
            for (int point = 0; point < 17; ++point) {
                ESP_LOGI(TAG, "point=%d x=%d y=%d", point,
                    result.keypoint[2 * point], result.keypoint[2 * point + 1]);
            }
        }
        memory("after_inference");
        vTaskDelay(pdMS_TO_TICKS(200));
    }
    heap_caps_free(img.data);
    ESP_LOGI(TAG, "BENCHMARK_DONE static image only; not a camera/posture/cloud test");
}
