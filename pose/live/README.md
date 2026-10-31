# BF3901 + YOLO11n-Pose + experimental posture viewer

Public source export, 31 October 2026. The ESP32-S3 captures a new BF3901 frame,
runs YOLO11n-Pose on the board, and sends a preview and matching COCO keypoints
over USB serial. The Python/Tkinter viewer draws the person box and skeleton.
The optional front-view posture experiment compares shoulder tilt, head drop
and torso lean against a personal calibration baseline.

This is a separate application from Lamp Studio. It has no voice, servo or
cloud action integration, and cannot run concurrently with the lamp firmware
on the same board. Close other serial controllers before using it. Starting
the desktop window is offline; clicking Start opens the board connection and
may reset it. This repository upload does not change the connected hardware.

## Files

- `host/live_pose.py`: request/response viewer, rotation, frame validation,
  skeleton overlay, explicit result saving and stop/close handling.
- `host/camera_wire.py`: serial transport, unique CH343 selection, UYVY/RGB/PNG.
- `host/posture.py`: experimental relative posture measurements and debounce.
- `host/test_*.py`: simulated transport, geometry, posture and board-selection tests.
- `firmware/main/`: camera capture and on-board YOLO inference source.
- `firmware/sdkconfig.defaults`, `firmware/partitions.csv`: original build settings.
- `prebuilt/`: original application image, SHA-256 and installation boundaries.

## Desktop setup (Python 3.11+)

From the repository root, run the existing `Setup-Windows.ps1`, or install
`pose/live/requirements.txt` into your chosen Python environment. Tkinter is
required. No desktop Ultralytics/YOLO package is needed: inference runs on the
ESP32-S3, while the host interprets its output.

```powershell
.\.venv\Scripts\python.exe -c "import tkinter, serial; print('OK')"
.\.venv\Scripts\python.exe -B pose\live\host\live_pose.py
```

Alternatively double-click `launch_pose.cmd`. Start is explicit in the UI.
The board must already run compatible live-pose firmware; the lamp diagnostic
firmware and static benchmark do not implement this protocol.

One connected CH343 board (VID `1A86`, PID `55D3`) is selected automatically.
With multiple matching devices, first inspect their identifiers and set the
intended serial in the same terminal before launching:

```powershell
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
$env:LJWB03_SERIAL = 'YOUR_CONFIRMED_BOARD_SERIAL'
.\.venv\Scripts\python.exe -B pose\live\host\live_pose.py
```

The viewer refuses zero or multiple matches. It never chooses an arbitrary COM
port. Baud is 921600. Source contains no original board identifier or machine
paths. Only one serial application can own the port at a time.

The sensor supplies 240 x 320 UYVY; board conversion and selected rotation
produce the model input. The serial preview is 120 x 160 before rotation.
Default rotation is 90 degrees clockwise. Frame offsets, lengths, FNV32,
frame/result IDs, rotation and coordinates are checked before drawing a result.
Missing points remain missing; the model interface supplies a box score but
no per-keypoint confidence. Display enlargement does not create image detail.

Stop waits for an ongoing inference, requests no further frames and releases
the port. Raw frame/PNG/JSON are stored only when Save is clicked (or the
explicit `--frames N` capture mode is used). Local serial logs go to
`pose/live/evidence/`; saved pictures go to `pose/live/captures/`. Both paths
are ignored by Git. Keep personal captures and device backups local.

## Posture experiment

Use a fixed, bright, frontal single-person view with nose, both shoulders and
hips visible. Click Calibrate and hold a comfortable pose for three valid
results. Shoulder/head/torso thresholds are provisional values of
0.12/0.15/0.18 shoulder widths. An alert needs at least 30 seconds and three
valid abnormal results. Missing points, multiple people, stale samples and
direction changes interrupt judgment. Restarting clears calibration; after
moving the camera or changing people, recalibrate manually.

These are uncalibrated 2D posture-change cues, not proven slouch/fatigue or
medical detection. Frontal 2D points cannot reliably resolve forward/backward
depth. Missing hips disable torso judgment. The program cannot identify a
person swap or camera movement automatically. No robot motion is triggered.

## Firmware dependencies and build boundary

The historical build used ESP-IDF 5.4.1, ESP-DL 3.3.14, COCO Pose 0.4.1 and
`YOLO11N_POSE_S8_V1`. ESP-DL sources are referenced at
`5acd1c9992af4afb0fa80c221a676982b11381b8` (see `../README.md`). Camera
components `esp_video` and `esp_cam_sensor` were 2.2.0, manifest source revision
`ac5d2ac96d63f5222cff77d90a4409fb0c3b8c76` in
`https://github.com/espressif/esp-video-components`.

Third-party SDK/component sources and model weights are not copied here.
Prepare the original compatible component set, retaining its licenses:
`coco_pose`, `esp-dl`, `dl_fft`, `esp_new_jpeg`, `esp_video`, `esp_cam_sensor`,
`esp_sccb_intf`, `cmake_utilities`, `esp-dsp` and `usb_host_uvc` plus their
declared dependencies. Keep paths usable by the Windows ESP-IDF linker;
spaces/non-ASCII precompiled-library paths caused issues in the original build.
In an activated ESP-IDF 5.4.1 shell:

```powershell
$env:YOLO_COMPONENTS_DIR = 'D:\prepared-components'
idf.py -C pose/live/firmware -B D:/yolo-live-build -DIDF_TARGET=esp32s3 build
```

This is a build command only. The portable CMake entry point requires that
explicit dependency directory and is not an offline dependency installer.
The exported portable firmware build has not been rebuilt in this upload
task; the included historical application retains its original checksum.
Read `prebuilt/README.md` before considering a separately authorized flash.

BF3901 wiring: 3.3V/GND, SDA21, SCL47, VSYNC4, PCLK9, D0=8, PWDN41;
HREF/D1 unused. The tested adapter supplies its own oscillator (no external
XCLK). GPIO8/9 conflict with common MPU6050 wiring. Disconnect power before
rewiring and keep mechanical actuators unpowered during camera work.

## Evidence and limits

Local 30 October records report five consecutive capture/inference cycles,
zero timeouts, mean inference 7239.92 ms and roughly 9.51 s between captures.
All five were dark-scene/no-person results. An older 29 October image had one
person at score 0.7311, before the stream-format lifetime fix. These historical
observations do not prove latest-firmware bright-scene recognition, sustained
reliability or real-person posture accuracy. Private images, USB identity and
raw logs are excluded. This upload performs software checks only, no board
connection, flashing or motion.

Run the hardware-free checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s pose/live/host -p "test_*.py" -v
```

Original host/firmware source comes from the team's camera-pose project and
the later posture experiment. The retained sensor-format storage and refresh
in `camera_main.c` fix an earlier stream restart lifetime error. Geometry
design references (no copied source/weights):
`https://github.com/aaron888hacker/-yolov8-` and
`https://github.com/Yoadkk/postureGuard`. Upstream SDK/model ownership and
licenses remain with their authors; see `../../THIRD-PARTY.md`.
