**30 October: eight-sound lamp firmware installed and verified. Water and stretch sounds are now available on the board. Earlier pending-install notes below are historical.**

## Ready-made starter poses (29 October)

Both **Water break** and **Stretch with me** now have editable starter positions, alongside Slump. You can calibrate these instead of teaching from scratch.

| Pose | Lift GPIO12 | Middle GPIO10 | Head GPIO11 |
|---|---:|---:|---:|
| Upright/start | 1000 | 600 | 1500 |
| Slump | 1100 | 800 | 1550 |
| Water invitation | 1050 | 750 | 1600 |
| Stretch | 950 | 550 | 1400 |

Values are microseconds. Upright follows the earlier starter profile with a centred head; the new small offsets are estimates, not calibrated physical directions. Use **Adjust routine → Save routine edits** to change any pose, or adjust the actual joints in **Teach lamp poses** and save the current position. **Load all slow starter poses** restores all four presets without moving anything. Defaults: six seconds per movement, maximum60µs/s; very small moves may finish earlier due to the firmware minimum10µs/s.

To run: reopen **Desktop → Hackathon-ESP32S3 → Lamp Demo**, connect, check external power/common ground, support the lamp and choose **1. Set starting pose**. Then press **Water break** or **Stretch with me**. First engagement can jump; STOP if a bend goes the wrong way. Base stays stationary. Place the bottle in front at the spot the gesture indicates. The eight-sound firmware is installed; both robot routines are available after setting the starting pose.

# Lamp actions: slump, water and stretch

Open **Lamp Demo** in Desktop → Hackathon-ESP32S3. Reopen the app to load this update; release outputs and support the lamp before closing a connected controller.

## Preview now

Choose **Robot chirps** or **Musical tones** in **Play the interaction**, then open **Sound previews**. **Preview stretch + happy ending on laptop** plays an encouraging rising cue, a pause and a happy finish. It works without the board. Nothing plays or moves automatically on launch or connection.

All eight sounds are original local synthesis, with no film samples or downloaded recordings. WAV previews and robot-ready16kHz mono PCM files are in `sounds`. The stretch preview's pause is illustrative; actual timing follows the taught motion and audio completion.

## What is ready

The six-sound slump/water firmware was installed and its connection verified on29October; see `installation.json`. The new eight-sound stretch firmware is prepared separately in `firmware/lamp-demo.bin`. **Update30October: the stretch update is installed; see installation.json.** No hardware was accessed during this stretch update. An older board program keeps stretch controls disabled while existing slump/water actions remain available.

Installation later must preserve Wi-Fi/NVS/model/partition data, back up the current application and update only the application at0x20000 after checking board identity and released outputs. Do not use generic full-flash commands from build output.

## Connections and teaching

- GPIO12: lift MG90S; GPIO10: middle SG90; GPIO11: lamp-head tilt SG90.
- GPIO15 continuous base stays stationary for these routines.
- Servos use external5V power and share ground with the board.

In **Teach lamp poses**, enter suitable limits and starting pulses. With the lamp supported, engage joints individually. First engagement can jump because no position sensor reports where the servo is. With all three engaged, use small −/+ adjustments to save the poses you need:

| Pose | Shape to teach |
|---|---|
| Upright | Comfortable, stable resting position |
| Slump | A modest droop, with the head looking down |
| Water bottle | Looking toward the bottle's marked fixed spot |
| Comfortable stretch | A small lift/opening of the arm and gentle upward head tilt |

Starter poses are supplied above. You can replace them by teaching, or edit the pulse values directly in Adjust routine. Existing calibrated poses are preserved; missing water/stretch poses in the current saved profile were filled with the starters.

Start with a modest stretch, not a fully straightened linkage or a servo end stop. The earlier500..2500µs values are electrical command limits; the new lamp may need narrower mechanical limits. The STL does not establish horn zero positions or collision-free travel. The initial upright lift/middle values come from the earlier starter profile; actual clearance must still be checked on this lamp.

## Action sequences

**Slump / Recover:** the arm links move gradually, then the head finishes its motion, with the selected sound. The final pose holds until another command.

**Water break:** return upright → gesture toward taught bottle spot → play invitation → hold1.2seconds after the cue → return upright. No bottle recognition or drinking detection. Place the bottle within the forward/head-tilt gesture range because the base does not turn.

**Stretch with me:**

1. Settle upright.
2. Play a rising invitation while lifting toward the taught stretch pose; the head follows in a second stage.
3. After commanded movement and cue completion, hold for2seconds.
4. Relax gently to upright, then play a happy finishing chirp or musical phrase.

Stretch uses at least3seconds for each full movement even if a shorter movement time is entered. The current slow profile caps motion at60µs/second, with firmware updates capped at10µs. A large change can take longer. The sequence duration depends on the saved distance, movement time and speaker delays. This is timed animation, not feedback that the person actually stretched.

**STOP movement + sound** cancels the remaining sequence, including any automatic return and final cue, and holds current commanded targets while communication is healthy. **Release outputs**, closing, or loss of communication can let the lamp fall; support it before releasing. Buttons are disabled while a routine runs. No camera, microphone, MPU6050 or LJYD trigger is required for these manual demonstrations.

## Validation and limits

Software tests cover both sound styles, motion endpoints, limits, old profile compatibility, firmware capability gating, cancellation, command parsing limits, audio format/clipping and idle UI behaviour. The firmware is built for ESP32-S3. Physical clearance, load, motion quality and speaker timing still need observation on the assembled lamp. Commanded completion is not measured joint feedback.
