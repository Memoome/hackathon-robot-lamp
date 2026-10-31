# Hello demo

Open **Hello Demo.lnk** inside **Desktop → Hackathon-ESP32S3**. The manual **Arm Control** shortcut remains available separately. Close other serial controllers before connecting to either window.

No microphone is used. Nothing moves or plays on launch. This demo requires external servo power and common ground, as confirmed by the user.

## Run a take

1. Click **Connect**. The window checks the intended board and robot audio module.
2. Confirm external servo power, common ground, mechanical clearance and cable clearance using the checkbox.
3. Click **1 · Set starting pose…** and confirm only when the arm has room. First engagement can move suddenly because shaft positions are not measured. If its positions are already known to this controller, returning to start uses the smooth ramp described below; otherwise the start targets are engaged directly. Support/unload it if needed.
4. Check the plate orientation and manually align the base's starting direction. The continuous base has no angle sensor.
5. Click **2 · Run greeting**. The base starts its board-timed one-second turn, then all three joints begin smooth ramps together in the next short serial command. The small serial-command gap avoids the SDK's eight-argument limit.
6. The robot plays **Hello! through its attached speaker** after the final joint targets have been acknowledged, the base turn has ended, and a 0.5-second settling pause has elapsed.

| Joint | GPIO | Starting pulse | Final pulse |
| --- | --- | --- | --- |
| Lift | 12 | 1000µs | 1300µs |
| Middle | 10 | 600µs | 1900µs |
| End plate | 11 | 2500µs | 500µs |

Each joint advances at **600µs/second**, equivalent to **300µs per 0.5 seconds**, using small changes made on the board approximately every10ms. Normal changes are about6µs, with a10µs cap on each update to avoid catch-up jumps. The final change clamps exactly to the endpoint. A joint that arrives sooner holds while the others continue. They start together; they do not all finish at the same time. Returning from a known end pose to the starting pose is smooth too.

Approximate pulse milestones during the smooth ramp are:

| Time (seconds) | Lift | Middle | Plate |
| --- | --- | --- | --- |
| 0.5 | 1300 | 900 | 2200 |
| 1.0 | 1300 | 1200 | 1900 |
| 1.5 | 1300 | 1500 | 1600 |
| 2.0 | 1300 | 1800 | 1300 |
| 2.5 | 1300 | 1900 | 1000 |
| 3.0 | 1300 | 1900 | 700 |
| About3.34 | 1300 | 1900 | 500 |

The base uses **GPIO15**, default **forward at 5% command strength** (1550µs with 1500µs neutral), for **1000ms timed on the board**. Direction, speed and neutral can be adjusted in the demo window before running. Its neutral stop pulse is sent for about 250ms, then that base signal is disabled. Timing does not measure angle: check cable twist and real stopping behaviour. Neutral can require trim.

## Stop, reset and repeat

- **STOP demo / hold pose** cancels remaining steps, freezes current position targets, requests a base stop and cancels audio. A cancelled motion sequence does not subsequently start Hello.
- **Release all…** disables position signals; support the arm first so it cannot fall. Closing has the same release concern.
- To repeat, use **Set starting pose** again. The base does not automatically return to its original angle; align it yourself before a take.
- **Test robot Hello only** plays just the sound when explicitly clicked. It does not move the arm. Use it to confirm speaker audibility before filming.

The software confirms command targets, not physical shaft positions. The 0.5-second settling pause is an allowance for movement, not sensor-confirmed physical completion. Increase mechanical clearance or pause the demo if a joint cannot keep up or binds. USB communication failure stops the sequence; the board bounds the base turn independently to one second and existing host-loss handling eventually releases position holds. No automatic resume occurs after a board reset.

## Sound and files

`hello.wav` was generated locally using Windows System.Speech speaking “Hello!”, without playing it during generation. The firmware embeds the 16kHz mono 16-bit PCM version (padded to320-byte audio frames), lasting about1.42seconds before playback padding/drain. The demo explicitly sets the robot speaker to **100% (hardware31/31)** before every Hello, including the sound-only test. No internet audio download or separate speech-recognition service is required.

- `greeting_demo.py`: the demo window and cancellable sequence controller.
- `hello.wav` / `hello-manifest.json`: generated sound and its format/hash.
- `greeting-demo.log`: commands and board responses, including failures.
- `demo-installation.json`: installed image hash, backup path and checks.
- `demo-hardware-check.json`: live GUI connection and inactive-output check.

Firmware preserves camera, manual arm and audio commands. The host starts the timed base with `arm_live scene` using the unchanged current pose, then starts/renews all three joint ramps with `arm_live glide`. Both fit the SDK's eight-argument parser limit. The earlier nine-argument `glide_scene` request was rejected by the serial parser and is no longer sent. Base timeout stops only the base, so it does not interrupt longer joint ramps. `audio_test hello` retains persistent playback-result status. Tests run the actual SDK tokenizer together with the installed C ramp functions using simulated hardware/time; they reproduce the old failure and verify the corrected sequence, reverse base,600µs/s, <=10µs changes, exact endpoints and base independence. Host tests cover speech ordering, cancellation, max-volume-before-Hello and UI layout. Verification issues no valid hardware motion or playback. User has confirmed the speaker Hello is good; observe the corrected gesture before filming.
