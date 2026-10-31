# Four-servo hold-to-move control

Open **Arm Control** in **Desktop → Hackathon-ESP32S3**. This version opens `live_control.py` and requires the new `arm_live` firmware. Older calibration tools remain in the source folder; close them before connecting. Nothing connects, engages or moves on window launch.

## Wiring

Turn power off before changing connections. Use board GPIO labels.

| Part | Signal GPIO | Control type |
| --- | --- | --- |
| Lift MG90S | 12 | Position target, 500–2500µs |
| Middle SG90 | 10 | Position target, 500–2500µs |
| End-plate SG90 | 11 | Position target, 500–2500µs |
| NEW base MG90S | **15** | Continuous rotation, direction/speed |

All servo grounds must join board GND. Servo red wires need suitable regulated 5V power. The camera stays on 3.3V, SDA21, SCL47, VSYNC4, PCLK9, D0=8 and PWDN41. GPIO15 does not overlap that mapping. GPIO13 remains assigned to the earlier vibration-module driver and is not used for this base.

The board's 5V current rating is unverified. For the complete arm, use a suitably rated separate regulated servo supply with common ground; do not join its positive rail to the USB-powered board +5V. If using board 5V for bench checks, select **Board 5V bench** and power **one unloaded servo at a time**, disconnecting the other red power wires. Software changing one target at a time does not reduce the combined holding/startup current of four connected servos.

## Move the position joints

1. Close the earlier controller/serial monitor. Support the arm before releasing any current hold. Click **Connect** in the new window.
2. Select the actual power mode and check the wiring/clearance box.
3. Under **Starting poses / wiring**, set the explicit starting pulse for a joint if needed (500–2500µs). The existing saved end-plate start of 2500µs is imported; other unsaved starts default to 1500µs. Nothing moves when you edit these values.
4. Click **Engage…** for a joint. Confirm only with room for that first move: its physical starting position is unknown. Support/unload it, and remove the linkage or horn first if needed. The first engagement cannot be made reliably gentle without knowing the actual position.
5. Choose **Joint target speed**. Default **100µs/second** changes the command over the full 2000µs range in about 20 seconds. 25 is slower; 600 is faster. This controls the rate of the command, not measured shaft speed.
6. **Press and hold ↑ or ↓**. The target changes gradually until release or the 500/2500µs limit. Use **Reverse arrows** for a joint if its mounting makes the direction inconvenient.
7. Releasing an arrow freezes the last target. **STOP motion / hold pose** also freezes motion. With a separate supply, initialized joints keep holding. Bench mode releases the signal about 0.7 seconds after motion stops; the joint may sag. Bench initial engagement allows roughly five seconds to begin jogging before releasing.

The pulse/range display is the board's last target, not measured shaft feedback. User confirmed 500–2500µs is acceptable for the three position joints; the software still cannot detect collisions, stall, load, or cable snagging. Independently valid joint ranges do not guarantee every combination is mechanically clear.

## Turn the continuous base

The user confirmed **500µs = reverse maximum, 1500µs ≈ stop, 2500µs = forward maximum**. This is a continuous-rotation servo, so pulse width controls direction/speed rather than angle.

- Start with **Base speed command = 5%**. Hold **←** or **→** to turn; release to send neutral and stop driving rotation.
- Speed percentage is the fraction of command range away from neutral, not measured RPM. Low settings may not overcome deadband or load. Raise gradually if needed.
- If the base creeps at neutral, change **Stop neutral** a few microseconds around 1500 and click **Test stop neutral**. A test sends a brief neutral pulse and then turns that signal off. It can cause movement if the entered value is not the actual neutral, so keep clearance.
- On release, the firmware sends neutral briefly, then disables the base signal. This does not provide a mechanical brake or guaranteed instantaneous stop; observe the actual servo response.
- There is no base angle, measured number of turns, or automatic cable-twist limit. Watch the wires and reverse before they wind around the base. It cannot hold a chosen base angle without additional feedback/control hardware.

## Stopping and connection loss

Releasing the mouse, leaving focus, minimizing the window, or pressing STOP cancels the requested motion. The UI also supplies a heartbeat while held. The serial worker keeps a current motion intent rather than queuing a sequence of future steps, so old steps are not replayed after release.

The board independently expires a movement request after **400ms** without renewal: position ramps freeze and the continuous base receives neutral. A delayed firmware task freezes rather than jumping to catch up. Separate-supply position holds expire after about **five seconds** without host contact. Normal release latency also includes serial transmission/processing; commands are not instant physical braking.

**RELEASE ALL**, closing, unplugging or losing power can let the arm fall. Support it first. Release turns position signals off, rather than supplying a mechanical brake or disconnecting servo power.

## What was checked

The actual firmware motion functions were compiled and run on the PC with simulated hardware/time. Tests passed for ramp rate, endpoint clamping in both directions, leaving an endpoint, release freeze, renewal expiry, task-delay freeze, base reverse/forward/neutral, base timeout and output-off, and invalid command rejection. Host tests passed for protocol decoding, base command conversion, UI deadman, mouse release cancellation, no motion on launch and layout.

`live-installation.json` records device flash/boot verification. Hardware checks deliberately send no valid engagement/jog/base commands: physical movement, load capacity, base neutral accuracy and speed still need user observation. The camera firmware is preserved. A new application backup is made before the app-only update; bootloader, models, settings and partition table are not rewritten.

Files: `live_control.py` is the new UI/serial worker; `live-commands.log` records board replies; `live-installation.json` is the installation record. `calibration.py` remains the earlier endpoint-teaching tool. `arm_controller.py` remains its shared legacy transport. Firmware lives in `C:\LJWB03\project\apps\main\actuator_test.c`.
