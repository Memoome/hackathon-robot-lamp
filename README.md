# Expressive Robot Lamp · LJWB03 / ESP32-S3

A hackathon companion lamp with four servos, an eight-LED ring, camera, microphone and speaker. **Lamp Studio** provides visual calibration, live dragging, saved checkpoints and animated motion/light/sound previews.

## Start here (Windows)

Install Python 3.11 or newer with Tkinter, clone this repository, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Windows.ps1
```

Double-click **launch_studio.cmd**. Previews work without hardware. For USB, connect one CH343 board (VID 1A86 / PID 55D3), or set `LJWB03_SERIAL` to choose among several. For Wi-Fi, use **Wireless setup** to save a 2.4GHz network and pair this PC via USB, then **Find lamp & enable wireless**. See [WIRELESS.md](apps/LJWB03-Lamp-Demo/WIRELESS.md). Each teammate needs their own local pairing settings; credentials are not included.

Connection and automatic reconnection never engage motors or resume an interrupted action. Keep the board powered after removing laptop USB. Servos use their separate regulated supply with common ground. The project board's header power-input capability has not been verified; USB-C power is the documented route.

## Current controls and actions

- Lift MG996R → GPIO12; elbow MG90S → GPIO10; head SG90 → GPIO11.
- **Current Studio base is an SG90 position servo → GPIO15.** The former continuous MG90S requires its old speed-control mode; do not connect it and use the position controls.
- Eight WS2812 LEDs: DI → GPIO1 through the recommended data buffer/resistor. Full map: [GPIO-USAGE.md](GPIO-USAGE.md).
- Slump, Water break, Stretch with me, Sad and Happy have coordinated previews. Stock actions use smooth bounded motion, sound cues and changing ring colour/brightness. Water points toward a configured bottle direction; it does not detect a bottle. Sad remains curled with dim blue light. Happy adds base wiggles, head bobs and a synthesized chuckle. Stretch includes its closing ahhh sound.
- Each preview opens a larger window showing the lamp, base direction, phase, sound cue, hue, RGB output, brightness and progress. Preview sends no hardware commands. Use **Run previewed plan** only after reviewing and explicitly engaging the supported lamp.
- The locked **final draft** profile stays protected in Studio. Loading it creates an editable working copy. Profiles and drawings estimate commanded geometry; there are no joint encoders or physical collision/load measurements.

The three bending joints retain 500–2500µs software access and bounded eased motion. Electrical bounds do not establish mechanical clearance. Preview/board timing can differ under network delay, sound buffering and physical load. STOP cancels subsequent motion/audio/colour updates; Release removes holding torque.

## Firmware and integration status

**Newest shared application: [lamp-action-lights.bin](firmware/prebuilt/lamp-action-lights.bin)**, with checksum in [action-lights-manifest.json](firmware/prebuilt/action-lights-manifest.json). It retains paired Wi-Fi control/OTA, LED commands and ten sound slots. Older images are recovery references; LED-only and original demo images do not preserve wireless support. See [firmware instructions](firmware/README.md) before updating. No upload occurs just by launching Studio.

Wi-Fi discovery/status, paired control and same-image OTA/rejoin were verified on the project board. A speaker-only robot chirp completed over Wi-Fi. The newest application installation verified outputs off and audio ready with ten sounds; that does not verify assembled movement, acoustic quality or light output. Firmware checksums identify each build separately.

**LJYD voice conversation/action integration remains separate work.** Local Wi-Fi control is not cloud authentication. The SDK contains voice/agent modules, but the diagnostic does not establish a working live cloud conversation. Named cloud actions still need explicit mapping to the lamp controller. Public source requires each developer's own product configuration; no shared product secret is supplied.

Vision remains a separate application from lamp motion/voice. `pose/benchmark` contains the static-image benchmark; [pose/live](pose/live/README.md) contains BF3901 capture, on-board pedestrian detection and presence decisions, automatic JPEG transfer, PC-side YOLO26 pose/posture processing, and the local web viewer. See [the current vision architecture and acceptance status](docs/VISION-POSE-ARCHITECTURE.md). The older on-board YOLO11n-Pose image is a historical reference, not the current pipeline. Scene accuracy and concurrent integration with lamp motion/voice remain unverified. MPU6050 is not assigned in the lamp and is not a servo encoder.

## Where everything lives

| Path | Purpose |
|---|---|
| `apps/LJWB03-Lamp-Demo/visual_control.py` | Main Studio interface |
| `apps/LJWB03-Lamp-Demo/expressive_routines.py` | Motion, lighting and gesture curves |
| `apps/LJWB03-Lamp-Demo/wireless_*.py` | Paired Wi-Fi transport, setup and updates |
| `apps/LJWB03-Lamp-Demo/profiles/` | Reference calibration/checkpoints |
| `apps/LJWB03-Lamp-Demo/sounds/` | Original robot and musical cues |
| Other `apps/` folders | Earlier manual arm, Hello, mic, camera and cloud setup tools |
| `firmware/overlay/` | Application overlay for the organizer's compatible SDK |
| `firmware/prebuilt/` | Application-only builds and checksums |
| `hardware/` | Lamp STL and supplied reference documents |
| `pose/` | Static benchmark and separate board-detection / PC-pose pipeline |
| `docs/VISION-POSE-ARCHITECTURE.md` | Current vision architecture, protocol and acceptance status |
| `tests/` | Simulated hardware and protocol checks |

Older controller tools assume their original hardware modes. Use Studio for the current position base. See [Studio guide](apps/LJWB03-Lamp-Demo/VISUAL-STUDIO.md); newest sections come first and supersede historical behavior below them.

## Teammates: build on this

[Fork this repository](https://github.com/Memoome/hackathon-robot-lamp/fork), commit changes in your fork and open a pull request to `main`. See [CONTRIBUTING.md](CONTRIBUTING.md). Direct pushes require an owner invitation. Update your clone using `git pull --ff-only`.

This repository is a portable reviewed export, not an automatic bidirectional mirror of the original laptop. Private Wi-Fi/pairing files, tokens, device backups, recordings, photographs, raw conversation history, installed tools and the complete vendor SDK are excluded. Obtain the compatible SDK/toolchains separately.

## Tests and provenance

Run the Python scripts in `tests/` using the prepared Python environment. `test_lamp_led.py` also needs host GCC. Tests use simulated hardware, and do not prove loaded mechanics. See [THIRD-PARTY.md](THIRD-PARTY.md) for SDK, sound and hardware-document provenance. No blanket license is asserted over third-party material.

## Latest software update · 31 October 2026

USB runtime communication now uses **921600 baud** across the host tools and current firmware. Use **firmware/prebuilt/lamp-921600.bin** with its 921600-manifest.json checksum. The project board's installation and non-moving USB status reply were verified. Older prebuilt applications can use a different USB baud; do not mix them with these host defaults. The audio-module UART remains 2000000; Wi-Fi has no serial baud rate. Apply firmware/usb-baud.defaults to the vendor build settings when rebuilding; qm_config.h also carries the new debug baud.

**Disable base rotation** is checked by default in Actions and the expanded preview. It excludes base movement from generated actions, custom routines and their robot playback, while preserving arm, light and sound behavior. Manual base controls remain available. Changing this option invalidates an existing preview plan; save an editable profile to retain the preference. The Actions shortcut/default tab and preview starting base direction were corrected. Connection/playback diagnostics and the live performance view are included in Studio.

Camera capture now waits for the complete CAM_END transfer marker. Live camera operation is still unverified; this is not a claim that camera troubleshooting is finished. LJYD action integration remains pending; no proposed JSON action protocol has been implemented just by discussing it.
