idf_component_register(SRCS "app_main.cpp"
    INCLUDE_DIRS "." REQUIRES coco_pose esp_timer esp_psram
    EMBED_FILES "bus.jpg")
