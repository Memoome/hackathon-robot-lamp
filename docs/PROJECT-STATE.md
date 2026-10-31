# Team handoff · 31 October 2026

Hardware is an ESP32-S3 WB03 (16MiB flash/8MiB PSRAM), four-servo lamp, BF3901 camera and VB701N mic/speaker module. The position range requested by the team is500..2500µs. Joint1 is lift, joint2 middle/elbow and joint3 head tilt; continuous base is separate.

Lamp Studio contains two diagrams: top is command/model estimate, bottom is manually observed shape used for calibration. Saved full-range settings must not be shrunk to a few observed sample points. The cardboard reference profile is editable. Head face direction can be flipped separately from pulse calibration. The model has no collision/force/position sensing.

Latest choreography uses quintic easing and joint lags, a head-first slump/recovery, gentle bottle invitation and upward stretch/relaxation. One-click full previews play sound on the laptop; the same sampled plan can stream to the robot via existing glide commands. Agent-run software tests passed; loaded-arm behavior still depends on the user's physical calibration and observations.

The prebuilt lamp firmware has SHA256 abd5d0da2ae53e6094afdac37f51e7f194327bf7d8cabb4b3c1167a5703e6d0f. It was application-only flashed and digest verified on the original board; all outputs off/audio READY/eight sounds were confirmed. Firmware startup skips normal pose/voice-agent paths. Network setup is explicit and does not contain a cloud motor-action mapping.

Prior LJYD authentication did not obtain a successful session; the reason remains unconfirmed. Enter team identity locally in the setup UI; never share secrets in issues/commits. Future actions should be explicit local routines invoked by a verified cloud event contract.

Pose work is separate from the lamp firmware. The static-image benchmark remains under `pose/benchmark`. The additional `pose/live` export contains BF3901 capture/conversion, on-board YOLO11n-Pose inference, a host skeleton viewer, experimental baseline/debounced posture cues, software tests and the original 30 October application image with checksum. Its original build used ESP-IDF5.4.1, ESP-DL3.3.14 and COCO Pose0.4.1. Historical records show five dark-scene cycles with no timeouts, mean inference 7239.92ms and no people detected; this does not establish latest-firmware bright-scene performance, long-term reliability or real-person posture accuracy. The portable firmware entry point has not been rebuilt as part of the export. No board was connected or flashed during export. Integration with lamp/voice, concurrency and combined memory/performance remain team work. An attached MPU6050 would measure its own module's motion, not a person's pose or servo shaft position.

Public export excludes private credentials/history/captures and complete tools. Some historical guides describe earlier preparation stages; this state and README are the current overview.

## Latest motion update ·31October

Corrected action home to Reviewed Left Rest1000/1682/1101, preserving original checkpoints and calibration. Stock actions are now larger and distinct, ~4.5–5seconds at600µs/s: Slump curls inward/down with hesitation and recovery; Water reaches outward and nods twice; Stretch opens upward and releases gradually. Joint/head geometry drives generated targets; real non-Starter checkpoints still take priority. Tests cover both styles, exact return, pulse/rate bounds, left-side sampled paths and no profile mutation. Actual Studio-rendered key poses were visually inspected. Physical collision/load checks remain necessary; no hardware actions were sent for these updates.
