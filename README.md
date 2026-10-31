# Expressive Robot Lamp · LJWB03 / ESP32-S3

A hackathon desktop companion lamp with four servos, a camera, microphone and speaker. **Lamp Studio** provides calibrated visual control, live dragging, saved checkpoints, continuous gesture previews and three expressive actions: **Slump**, **Water break** and **Stretch with me**.

## Start here (Windows)

Install Python3.11 or newer with Tkinter, then clone this repository and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Windows.ps1
```

Double-click **launch_studio.cmd**. Previews work without hardware. For a different board, connect one CH343 USB device (VID1A86/PID55D3); when multiple matching devices are connected, set `LJWB03_SERIAL` to the intended board's serial number. Public source does not contain the original board's identifier.

The supplied **Lamp Cardboard Prototype** profile is a reference for our assembly. Check your own linkage and servo mounting before using its pulses. Visual calibration estimates commanded geometry; it does not provide physical position or collision feedback.

## Where everything lives

| Folder/file | Use |
|---|---|
| `apps/LJWB03-Lamp-Demo/visual_control.py` | Main Lamp Studio interface |
| `apps/LJWB03-Lamp-Demo/expressive_routines.py` | Motion design, geometry and eased gesture curves |
| `apps/LJWB03-Lamp-Demo/profiles/` | Saved cardboard prototype calibration/checkpoints |
| `apps/LJWB03-Lamp-Demo/sounds/` | Original robot/musical cues, WAV previews and embedded PCM |
| Other `apps/` folders | Manual arm/Hello, mic, camera, vibration module and Wi-Fi/LJYD setup tools |
| `firmware/overlay/` | Application changes to apply to the organizer's WB03 SDK |
| `firmware/prebuilt/` | Verified diagnostic lamp application and checksum; not a full flash backup |
| `pose/` | Static-image benchmark plus separate BF3901/YOLO live-pose source and experimental posture viewer |
| `hardware/` | Lamp STL and supplied board/component documentation |
| `docs/` | Development guides and architecture |
| `tests/` | Software tests; these never prove loaded-arm mechanics |

## Wiring

| Function | Signal |
|---|---:|
| Lift MG90S position servo | GPIO12 |
| Middle SG90 position servo | GPIO10 |
| Lamp-head tilt SG90 position servo | GPIO11 |
| Continuous-rotation MG90S base | GPIO15 |
| Camera SDA / SCL / VSYNC / PCLK / D0 / PWDN | 21 / 47 / 4 / 9 / 8 / 41 |
| VB701N audio TX / RX / flow | 40 / 39 / 38 |

Servos use a suitable separate regulated5V supply with ground shared with the board. Keep its positive supply separate from the USB board supply. Position commands span500–2500µs; this does not guarantee mechanical clearance. Base neutral is approximately1500µs; it controls speed rather than angle and has no heading feedback. Watch cable twist.

## Current status and boundaries

- Visual calibration, live control, USB reconnection, named profiles and complete gesture/sound previews are implemented.
- The diagnostic firmware supports servo ramps, camera/mic/audio tests and explicit Wi-Fi/LJYD setup. No motion occurs automatically on connection.
- Auto reconnect restores USB communication only. After disconnect, support and engage the lamp deliberately; interrupted motions do not resume.
- The three expressive routines share the same eased sampler in preview and hardware target generation. Actual transport delay, speaker buffering, load and backlash can differ.
- The LJYD voice-agent-to-action bridge is **not integrated**. Earlier registration did not establish an authenticated cloud session. USB connection and Wi-Fi connection are separate from LJYD authentication.
- Pose work includes the original static-image benchmark and a **separate BF3901/YOLO11n-Pose camera application** under [pose/live](pose/live/README.md), with a Python skeleton viewer and experimental calibrated posture cues. Historical inference was about 7.24 seconds per frame; latest-firmware bright-scene recognition, long-run reliability and real-person posture accuracy remain unverified. It is not integrated with lamp motion/voice, and combined memory/performance checks remain team work.
- LED/MPU6050 integration is not part of the completed lamp routines. MPU6050 is not a servo encoder.

## Teammates: build on this

**Anyone can contribute:** [fork this repository](https://github.com/Memoome/hackathon-robot-lamp/fork), add or upload your code in your fork, then open a pull request back to `main`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the exact steps. Direct pushes require an invitation from the owner for your GitHub username.

Fork the repository, create a branch, make changes and open a pull request. Suggested work areas:

1. **Motion/hardware:** calibrate physical poses, inspect preview, then validate clearance/load and tune gestures.
2. **Vision:** validate the separate live camera/YOLO source on the intended board, collect posture samples and tune the existing calibration/debounce, then design lamp integration.
3. **Cloud/voice:** finish product/device authentication in LJYD, bind the agent and implement an explicit local action-event handler.

To update a clone after teammates merge changes:

```powershell
git pull --ff-only
```

To share your changes, use a branch and pull request. Direct pushing to the owner's repository requires collaborator access; public visitors can already fork and propose changes.

The desktop launch workspace on the original PC links to files outside that folder. This repository includes the relevant actual sources as a portable export. It is not a live bidirectional mirror of that PC: commit/push changes in this clone, or refresh selected source files before committing. The existing desktop setup remains usable separately.

## What was intentionally excluded

Wi-Fi passwords, product/device secrets, account tokens, full flash/NVS backups, private recordings/photos, raw conversation exports, local logs/status snapshots, machine shortcuts, installed tools/IDEs, downloaded multi-gigabyte portable environments and the organizer's complete vendor SDK. The maintained technical guides replace private conversation history. Install toolchains from their official sources; obtain the supplied WB03 SDK through the hackathon organizers.

## Tests

```powershell
.\.venv\Scripts\python.exe -B tests\test_visual_lamp.py
.\.venv\Scripts\python.exe -B tests\test_expressive_routines.py
```

Tests use simulated hardware. Preview first and support the real arm before engagement/release. Only one controller can own the serial port at a time.

## Third-party material

See [THIRD-PARTY.md](THIRD-PARTY.md). Firmware overlays require the organizer's SDK and retain upstream notices; this repository does not grant rights to the omitted vendor SDK. Do not publish credentials in contributions.
