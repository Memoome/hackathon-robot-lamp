# Shared project state · 31 October 2026

## Boot return-to-rest source update · 1 November 2026

The lamp offline-audio firmware startup now turns the LED ring off, then applies
`return_rest.action.json` targets once: lift 1000, elbow 1682, head 1101,
SG90 position base 1500 microseconds. `tools/export_boot_rest.py` generates the
checked-in target header and package hash. Re-export and rebuild after changing
the package. This is a fixed startup target, not a general JSON action player.

Initial physical angles are unknown. Startup directly enables target PWM;
there is no claim of a smooth initial trajectory or measured homing. It holds
these commands locally without a PC lease until an explicit host command takes
over. Status/ping do not re-trigger or take ownership. Studio can claim a marked,
stationary boot-held pose without moving it, then the existing five-second host
watchdog applies. On connection, existing movement is frozen; ordinary stationary
held outputs retain mainline connection behavior without new motion. Only a
marked, fully active stationary boot pose is claimed. OFF releases; STOP
freezes and enters host-controlled holding. Neither restarts boot return.

Runs once per application boot, including reset/OTA restart, only after startup
initialization succeeds. Any target write failure releases all outputs and is
not automatically retried. Initialization or LED-off failure skips return.
The separate vision firmware is unchanged. Existing prebuilt binaries are unchanged.
Host tests compile and execute the actual startup function with injected PWM
failures and check generated targets against JSON. Full vendor firmware build,
flashing, loaded mechanics and power-on acceptance remain unverified.


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

## Visual action interaction branch · 1 November 2026

`feat/visual-action-interaction` connects fresh board presence reports from the
local vision service at port 8768 to Studio's existing Water and Stretch routines.
Sedentary for 10 seconds triggers Water (configured bottle direction and return);
continuous head-down observations spanning 5 seconds trigger Stretch (unchanged
lift, unfold, base sway, return, sounds and lighting). Starting continuous
capture with this branch's host sends `cam_test sit_limits 10 10` before streaming;
this is a session setting, not a flashed firmware-default change.

In Studio, connect and engage all four joints, then enable
“视觉联动：见人呼吸灯 · 久坐喝水 · 低头伸展”. Reports must be active, at most three seconds old,
with a stable present person, neither away nor standing, and a sedentary alert
with at least ten counted seconds. Each sitting episode is handled once. Busy or
unengaged episodes are consumed rather than queued; board rest/reset (`sit_s=0`)
rearms the next episode. Existing board rest reset remains two minutes away.
STOP, release, disconnect and connection errors disable automatic interaction.
Head-down uses the individual `head_down` level (watch/alert), not the main
posture label or its duration. Only distinct, calibrated fresh observations count;
unknown/stale data, a gap over four seconds or a busy controller breaks the timer.
One Stretch per head-down episode; a fresh `ok` observation rearms it. If both
conditions mature together, Stretch wins and that sitting reminder is consumed.
The compact presence API now includes posture verdict and timestamp, without images.
Restarting Studio resets its in-memory episode latch; enabling it during an
existing alert may trigger once. No settings or calibration profiles are changed.

Validation: automated trigger/Studio dispatch tests and host stream protocol
checks. No physical motion acceptance or firmware flashing was performed.
The vision and lamp applications remain separate firmware: the bridge requires
a working vision source and a separately reachable lamp controller. It does not
make one board run both firmware applications; do not open two USB controllers
against the same serial device. The existing Studio Windows audio dependency
also remains; Mac native Studio acceptance is outstanding. An already-running
vision service from another worktree must be restarted with this branch's host
for automatic ten-second threshold configuration to apply.

### Presence lighting

With visual interaction enabled and the lamp connected, standby is black.
The first fresh `present=true` report starts warm breathing immediately without
waiting for stable presence, calibration or the sitting threshold. Default colour
is RGB 255/213/154, brightness 5–25%, period four seconds. Actual onset includes
presence reporting, HTTP polling (0.5 s) and idle worker scheduling (0.2 s); this
is not a zero-latency board-local implementation. No servos need engagement for
lighting alone. False presence, stopped acquisition or data older than three
seconds requests black. Motion routines retain priority over background light
commands; when they finish, the latest presence state restores breathing/black.
Background commands run only in the existing controller worker while idle, so
there is no extra serial owner, queued animation or action-busy flag from fading.
STOP/disable requests black when the worker next becomes idle. A disconnected
lamp cannot be commanded off and can retain its last colour. Manual LED controls
disable visual interaction and take over lighting. This code has automated tests,
but no new physical light or motion acceptance has been performed.
