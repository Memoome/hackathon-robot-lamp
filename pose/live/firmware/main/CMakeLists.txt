idf_component_register(SRCS "camera_main.c" "pose_engine.cpp" INCLUDE_DIRS "." REQUIRES coco_pose esp_video esp_cam_sensor esp_driver_gpio esp_driver_spi esp_timer esp_psram)
