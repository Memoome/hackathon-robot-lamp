#include "qm.h"
#include "qm_work.h"
#include "offline_audio_test.h"
#include "bsp_io.h"
/* #include "bsp_mpu6050.h" */
#include "bsp_servo.h"
#include "bsp_vibrator.h"
#include "bsp_ws2812.h"
#include "voice.h"
#include "agent_app.h"
#include "ljyd_cloud.h"
#include "ljyd_provision.h"
#include "iot_control.h"
#include "pomodoro.h"
#include "ljyd_course.h"
#if defined(CONFIG_QM_POSE_SUPPORT) && CONFIG_QM_POSE_SUPPORT
#include "example_pose.h"
#endif

#if defined(CONFIG_APP_CAMERA_TEST) && CONFIG_APP_CAMERA_TEST
#include "bsp_camera.h"
#endif

#if defined(CONFIG_QM_ALARM_SUPPORT) && CONFIG_QM_ALARM_SUPPORT
#include "app_alarm.h"
#endif

#if defined(CONFIG_LJYD_PLAYBACK_SUPPORT) && CONFIG_LJYD_PLAYBACK_SUPPORT
#include "playback.h"
#endif

#include <stdio.h>
#include <stdarg.h>

int qm_vsnprintf(char *str, size_t count, const char *fmt, va_list ap)
{
    return vsnprintf(str, count, fmt, ap);
}

void app_main(void)
{
    qm_main();
}

void qm_application_start(void)
{
#if defined(CONFIG_OFFLINE_AUDIO_TEST) && CONFIG_OFFLINE_AUDIO_TEST
    offline_audio_test_start();
    return;
#endif
#if defined(CONFIG_QM_POSE_SUPPORT) && CONFIG_QM_POSE_SUPPORT
    example_pose_run();
#endif
    // if (bsp_servo_init() != QM_EOK) {
    //     QM_LOGE("main", "servo init failed");
    // }
    // if (bsp_vibrator_init() != QM_EOK) {
    //     QM_LOGE("main", "vibrator init failed");
    // } else {
    //     bsp_vibrator_pulse(BSP_VIBRATOR_PULSE_MS);
    // }
    // bsp_ws2812_example();
    if (qm_work_on_init() != QM_EOK) {
        QM_LOGE("main", "qm_work_on_init failed");
        return;
    }
    if (bsp_io_init() != QM_EOK) {
        QM_LOGE("main", "io init failed");
        return;
    }
#if defined(CONFIG_APP_CAMERA_TEST) && CONFIG_APP_CAMERA_TEST
    if (bsp_camera_early_init() != ESP_OK) {
        QM_LOGE("main", "camera early init failed");
    }
#endif
    /* if (bsp_mpu6050_init() != QM_EOK) {
        QM_LOGE("main", "mpu6050 init failed");
    } */
    if (voice_start() != QM_EOK) {
        QM_LOGE("main", "audio init failed");
        return;
    }
#if defined(CONFIG_LJYD_PLAYBACK_SUPPORT) && CONFIG_LJYD_PLAYBACK_SUPPORT
    if (playback_init() != QM_EOK) {
        QM_LOGE("main", "playback init failed");
    }
#endif

    if (ljyd_cloud_init() != QM_EOK) {
        QM_LOGE("main", "ljyd_cloud_init failed");
        return;
    }
    if (iot_control_init(ljyd_cloud_get_handle()) != QM_EOK) {
        QM_LOGE("main", "iot_control_init failed");
    }
    if (ljyd_course_init(ljyd_cloud_get_handle()) != QM_EOK) {
        QM_LOGE("main", "ljyd_course_init failed");
    }
    if (ljyd_provision_init() != QM_EOK) {
        QM_LOGE("main", "ljyd_provision_init failed");
    }
    if (agent_app_init(ljyd_cloud_get_handle()) != QM_EOK) {
        QM_LOGE("main", "agent_app_init failed");
    }

#if defined(CONFIG_QM_ALARM_SUPPORT) && CONFIG_QM_ALARM_SUPPORT
    /* 闹钟：开机即初始化（不要求已联网）。云端同步与响铃行为注册都在模块内部完成。 */
    if (app_alarm_init(ljyd_cloud_get_handle()) != QM_EOK) {
        QM_LOGE("main", "app_alarm_init failed");
    }
#endif

#if defined(CONFIG_QM_POMODORO_SUPPORT) && CONFIG_QM_POMODORO_SUPPORT
    pomodoro_init();
#endif
}
