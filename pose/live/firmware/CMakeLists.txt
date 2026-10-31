cmake_minimum_required(VERSION 3.16)

# Use an explicit directory containing the original component directories.
# No dependency downloads or hardware operations are performed by this file.
set(YOLO_COMPONENTS_DIR "$ENV{YOLO_COMPONENTS_DIR}" CACHE PATH "Prepared ESP-DL and BF3901 components")
if(NOT IS_DIRECTORY "${YOLO_COMPONENTS_DIR}")
    message(FATAL_ERROR "Set YOLO_COMPONENTS_DIR to the prepared component directory; see ../README.md")
endif()
set(EXTRA_COMPONENT_DIRS "${YOLO_COMPONENTS_DIR}")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(wb03_live_pose)
