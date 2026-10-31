# Pose detection: laptop preparation

Prepared for Arnav's WB03 / ESP32-S3, 29 October 2026.

The files needed to develop and build on-board pose recognition are on this laptop. The new test project is separate from the working robot firmware. Downloading and compiling does not install anything on the board.

## What each thing is for

| Thing | In simple terms | Where it is |
|---|---|---|
| ESP-DL 3.3.14 | The engine that runs a neural network on the ESP32-S3 | `C:\LJWB03\pose-lab\esp-dl-v3.3.14\esp-dl` |
| COCO Pose 0.4.1 | The code that turns a picture into body-point coordinates | `C:\LJWB03\pose-lab\esp-dl-v3.3.14\models\coco_pose` |
| YOLO11n-Pose S3 V1 and V2 `.espdl` files | Two prepared versions of the model's learned knowledge; V1 is selected for the first test | `models\coco_pose\models\s3` inside the downloaded source |
| FFT 0.8.0 and JPEG 1.0.2 libraries | Supporting maths and picture-reading code required by the engine | `C:\LJWB03\pose-lab\benchmark\managed_components` |
| ESP-IDF 5.4.1, compiler and Python | Existing tools that turn the source into a program the board can run | Existing `C:\LJWB03` kit; reused |
| Static-image benchmark | A small test that recognises people in the supplied `bus.jpg`, repeats three times and reports time and free memory | `C:\LJWB03\pose-lab\benchmark` |
| Build script | Compiles that test on the laptop; it does not install or run it on the board | `C:\LJWB03\pose-lab\Build-Pose-Benchmark.ps1` |
| Build results | The compiled program, packed model and logs | `C:\LJWB03\pose-lab\build` and `build.log` |
| `download-manifest.json` | Exact versions, source revision and file fingerprints to help another agent reproduce this setup | `C:\LJWB03\pose-lab` |

The official source checkout contains a few files for other Espressif chips. Only files under `models/s3` are selected for this board. A stock PC `.pt` model is not a directly installable ESP32 program. There is no need to install PyTorch, CUDA or a training environment to use these supplied models.

## How to find and build it

Open the desktop folder `Hackathon-ESP32S3`, then `Pose Detection`.

1. `Open Pose Files` opens the actual development folder.
2. `Build Pose Benchmark` recompiles the separate test. The window will say `BUILD ONLY complete` when successful. It never flashes the board.
3. `START-HERE.md` is this guide.

The equivalent PowerShell command is:

```powershell
& 'C:\LJWB03\pose-lab\Build-Pose-Benchmark.ps1'
```

Rebuilding alone will not add posture detection to the currently running board. The benchmark uses a supplied photo, not the connected camera, and does not start Wi-Fi, microphones, speakers or motors. Its firmware is intended for a separate installation/test step.

## What still needs implementing and testing

1. Install the benchmark through the existing backup-and-verification process, then measure actual recognition time and remaining memory on this particular board.
2. Connect the existing BF3901 camera capture code to this newer model. Convert a captured frame to the expected picture format and process one frame at a time.
3. Calibrate normal sitting posture for the camera's mounting position and distance. Require repeated reliable detections and a reminder cooldown. The model locates body points; our code decides when posture appears off.
4. Run camera recognition alongside Wi-Fi and voice, checking available memory and responsiveness. A standalone successful build does not prove these can all run together reliably.
5. Finish LJYD device authentication and verify its supported way of turning a device event into an agent conversation/spoken reminder. Define and test that connection; do not assume any arbitrary JSON event will trigger speech.
6. Connect named gestures to the already tested local motor routines if wanted.

The intended chain is: **camera → body points → our posture rules → sustained-posture event → configured LJYD response → speaker**, with any precise motor movement handled by our firmware.

## Existing board files to reuse

- Camera driver and tests: `C:\LJWB03\project\apps\main\camera_test.c`.
- Existing pose conversion and basic posture heuristics: `C:\LJWB03\project\apps\main\pose\yolo11_pose.cpp`. These heuristics are a starting point, not validated posture assessment.
- Existing voice agent: `C:\LJWB03\project\apps\main\agent\agent_app.c`.
- Existing LJYD/cloud code: `C:\LJWB03\project\apps\main\cloud`.
- Existing firmware recovery material: `C:\LJWB03\backup` and `C:\LJWB03\pc-setup-results`.

The current diagnostic firmware bypasses normal pose/voice-agent startup. The older product pose entry point tests `bus.jpg`; its camera example is disabled. Latest previously checked LJYD registration did not obtain a device ID. None of those gaps is fixed merely by downloading the new engine.

## Hardware and performance notes

The board was previously identified as ESP32-S3 with 16 MiB flash and 8 MiB PSRAM. This benchmark selects 240 MHz CPU, 80 MHz octal PSRAM, one S3 V1 model and a separate model partition. Its partition layout matches the existing project's layout, but a future installation must verify the actual board's partitions and backups again.

Do not use the generic full-flash commands printed by ESP-IDF against the current robot. Those also include a bootloader, partition table and model and could replace saved settings or working code if used carelessly. This preparation supplies a build shortcut, not an installation shortcut.

Espressif's current model documentation lists roughly 4.4 seconds of model execution per image on ESP32-S3 for its benchmark configuration. The old bundled model documentation lists roughly 28 seconds. These are reference measurements, not tests of our board or of simultaneous camera, network and audio operation.

## Official sources and licences

- [ESP-DL v3.3.14 release](https://github.com/espressif/esp-dl/releases/tag/v3.3.14)
- [Pinned COCO Pose component](https://github.com/espressif/esp-dl/tree/v3.3.14/models/coco_pose)
- [Official static-image example](https://github.com/espressif/esp-dl/tree/v3.3.14/examples/yolo11_pose)
- [Current model benchmark documentation](https://github.com/espressif/esp-dl/blob/master/models/coco_pose/README.md)

Official downloaded files retain their included licence notices. The source checkout is pinned to commit `5acd1c9992af4afb0fa80c221a676982b11381b8`; it is separate from the project's older ESP-DL 3.2.4. Keep model and runtime versions together rather than replacing isolated model files in the working firmware.

## Preparation verification

The isolated ESP32-S3 build passed on this laptop using ESP-IDF 5.4.1 and GCC 14.2.0. The application is 1,404,864 bytes and the packed V1 model is 3,117,712 bytes; both fit the existing partition sizes. The required managed libraries are downloaded locally and their versions are locked. The official checkout is unmodified. No USB connection, reset, firmware write, camera capture, recording, playback or motor command was performed.
