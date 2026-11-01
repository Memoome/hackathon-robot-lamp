# Pose projects

The original static-image benchmark is retained below. The separate
[live camera/YOLO application](live/README.md) adds BF3901 capture, on-board
YOLO11n-Pose, a portable Python viewer and experimental calibrated front-view
posture cues. Launch its desktop UI with `live/launch_pose.cmd` after installing
the repository's Python dependencies. It requires compatible live-pose firmware;
the lamp application and static benchmark use different protocols.

The live project includes source, hardware-free tests and the historical
application binary with checksum. Model weights and third-party SDK sources
are obtained separately from their original sources. Neither pose project
runs concurrently with the lamp firmware. Do not flash merely to inspect code.
See `live/prebuilt/README.md` for the original image's compatibility boundaries.

## Original on-board static-image starter

This is a built static-image ESP32-S3 benchmark, not a finished live posture detector. The friend owns camera/inference integration. Do not flash this over the lamp firmware without backing up the current application and verifying model compatibility.

Install ESP-IDF5.4.1, then in pose/:

```
git clone --filter=blob:none --no-checkout https://github.com/espressif/esp-dl.git esp-dl
git -C esp-dl sparse-checkout init --cone
git -C esp-dl sparse-checkout set models/coco_pose
git -C esp-dl checkout 5acd1c9992af4afb0fa80c221a676982b11381b8
cd benchmark
idf.py set-target esp32s3
idf.py build
```

Managed COCO Pose0.4.1 sources and S3 models come from the pinned official repository. Build downloads required components. This project does not run concurrently with the lamp/network firmware yet. Measure actual RAM/inference time before promising real-time posture recognition. See docs/Pose-Detection-Setup.md for the original lab notes.
