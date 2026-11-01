# Shared project state · 31 October 2026

The current portable Studio includes Wi-Fi/USB transport, paired local discovery, explicit firmware updates, position-base control, visual calibration, locked final draft, live dragging and expanded animated previews. Lift12=MG996R, elbow10=MG90S, head11=SG90, current base15=SG90 position, ring1=8 WS2812 LEDs. Earlier continuous-base tools remain historical references.

Five stock actions are available: Slump, Water, Stretch, Sad and Happy. Arm/base movement, sound and lighting share the preview/playback plan. Water uses a configured bottle location. Software geometry is not physical feedback. Calibration and locked profiles were preserved.

Latest application: firmware/prebuilt/lamp-action-lights.bin, SHA256 f9c16d6b5f48971b290a490043850a2107f0f0123ca47a3ee4c19b522fa8c25e, 1943280 bytes, ten sound slots, wireless retained. Original-device application-only installation, outputs off and audio ready were recorded. Physical assembled actions/lights still need observation. Wi-Fi discovery/status, earlier OTA/rejoin tests and a speaker-only chirp were verified separately. Current source is a snapshot; running source does not itself flash the board.

LJYD live authentication/conversation/action mapping and concurrent vision remain separate integration tasks. The public overlay contains no configured product secret. Pair each PC and enter Wi-Fi/product credentials locally. Do not publish local settings, full-flash/NVS images or private captures.

Read README.md for current behavior and firmware/README.md for update/SDK requirements. Studio guide newest sections supersede historical sections. This export preserves the existing teammate contribution history.

## Latest software update · 31 October 2026

USB runtime communication now uses **921600 baud** across the host tools and current firmware. Use **firmware/prebuilt/lamp-921600.bin** with its 921600-manifest.json checksum. The project board's installation and non-moving USB status reply were verified. Older prebuilt applications can use a different USB baud; do not mix them with these host defaults. The audio-module UART remains 2000000; Wi-Fi has no serial baud rate. Apply firmware/usb-baud.defaults to the vendor build settings when rebuilding; qm_config.h also carries the new debug baud.

**Disable base rotation** is checked by default in Actions and the expanded preview. It excludes base movement from generated actions, custom routines and their robot playback, while preserving arm, light and sound behavior. Manual base controls remain available. Changing this option invalidates an existing preview plan; save an editable profile to retain the preference. The Actions shortcut/default tab and preview starting base direction were corrected. Connection/playback diagnostics and the live performance view are included in Studio.

Camera capture now waits for the complete CAM_END transfer marker. Live camera operation is still unverified; this is not a claim that camera troubleshooting is finished. LJYD action integration remains pending; no proposed JSON action protocol has been implemented just by discussing it.

## Separate vision pipeline

The merged `pose/live` source runs pedestrian detection and presence states on the board, automatically sends JPEG frames when a stable person is present, and runs YOLO26 pose/posture processing on the PC. A local web client displays matching frames and results. The current firmware source no longer runs the older on-board YOLO11n-Pose model; its checked-in prebuilt image remains a historical reference. Follow [VISION-POSE-ARCHITECTURE.md](VISION-POSE-ARCHITECTURE.md) for recorded measurements, current protocol and remaining acceptance work. Scenario-level posture accuracy and concurrent lamp/voice integration are not established by merging these sources. No hardware is flashed by this merge.
