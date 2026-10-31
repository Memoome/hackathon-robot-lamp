# Three-servo arm control

**Greeting demo:** [GREETING-DEMO.md](GREETING-DEMO.md) describes the separate Hello Demo window: the supplied start/end poses, synchronized 300µs target steps, a one-second base turn and generated Hello playback on the robot speaker. Manual Arm Control remains available.

**Latest version:** the four-servo press-and-hold controller is documented in [HOLD-TO-MOVE.md](HOLD-TO-MOVE.md). It adds the continuous base on GPIO15. That guide supersedes the older interfaces below once the new firmware and shortcut are installed.

**Updated:** Arm Control now opens the observed-travel calibration window. Read [CALIBRATION.md](CALIBRATION.md) for current instructions. The generic-degree interface described below is the preserved older controller; its default angle scale did not calibrate the assembled arm.

Open **Arm Control.lnk** inside **Desktop → Hackathon-ESP32S3**. No servo moves when the window opens.

## Signal wiring

Turn off power before wiring. Use the board's **GPIO labels**.

| Servo | Signal wire |
| --- | --- |
| MG90S | GPIO12 |
| First SG90 | GPIO10 |
| Second SG90 | GPIO11 |

Signal is usually orange, yellow or white. Brown/black is ground; red is servo power. Check the particular servo's wire labels. These controls assume normal position servos; a continuous-rotation variant cannot use this angle display.

Keep the camera as previously connected: 3.3V, GND, SDA21, SCL47, VSYNC4, PCLK9, D0=8, PWDN41. Camera and servo signal pins do not overlap.

## Power now versus power for the arm

The board's 5V output current rating has not been established. Three loaded servos cannot be approved against an unknown power budget. Changing only one target at a time does not solve this: the other servos can still draw current while holding or starting up.

Until a suitable servo supply is available, use **One powered servo: brief test**. Disconnect the red power wires of the other two servos and remove load from the tested joint. Support the arm. The single powered servo can be connected to board 5V for a brief bench check, but that power path is still unverified. Stop and disconnect if there is buzzing, heating, a reset or erratic movement. Never use 3.3V for servo power.

For three-joint operation, connect all servo red wires to a suitable regulated 5V supply, all servo ground wires to its ground, and join that ground to board GND. Keep external +5V separate from board +5V while USB is connected. Select **Separate 5V supply: hold joints** only after that supply is connected and rated for the combined loaded/stall current. A power bank/charger label alone does not establish the board's pass-through rating.

## Move a servo

1. Close other serial apps, including the camera tester. Wait for **Board ready**.
2. Select the actual power setup. Check the wiring/clearance box only when it is true.
3. Support the arm and click **Start at 90°** for the powered servo. Confirm the dialog: this first command can cause a substantial movement because its starting position is unknown. Remove the horn or disconnect the linkage first if clearance is uncertain.
4. Click **↑** to increase the target angle or **↓** to decrease it. Default step is 2°. Select 1°, 5° or 10° if useful. Holding the mouse does not repeat moves.
5. In brief mode, each command lasts 0.7 seconds and then releases. In separately powered hold mode, previously initialized joints keep holding as you move another joint.
6. Support the arm before pressing **RELEASE ALL**, closing, unplugging or removing power. Release stops the signal; it is not a mechanical brake or power disconnect. The arm can fall under gravity. Loss of host communication also releases holds after about five seconds.

## Understand the angle and range display

The number is the **last angle command acknowledged by the board**. No shaft sensor is connected, so the app cannot measure actual position, detect a stall, or know if a released joint was moved by hand. It starts with **position unknown** and forgets positions after reconnect/reset/release. It does not restore motion on startup.

At a command of 100°, the nominal 0–180 scale has 100° downward and 80° upward remaining. A second line shows remaining travel within your configured limits. Default limits are **60–120°**, so at 100° those are 40° downward and 20° upward. Arrows disable at these limits. Physical up/down depends on how the servo is installed.

The initial pulse scale is **1000–2000 microseconds at 50Hz**. This is a cautious starting mapping; it does **not** establish that any particular servo travels a physical 180°. The existing kit source used a wider range for its original servo, but that is not calibration of these three units or the assembled arm.

In **Wiring and limits**, release first, then edit each joint's minimum/maximum and optional endpoint pulse calibration. Limits must include 90° and stay within 0–180°. Pulse endpoints must stay within firmware bounds (500–1500µs low, 1500–2500µs high, with high greater than low). Expand gradually with the linkage unloaded, observe actual motion, and stop before buzzing or mechanical contact. Arm geometry may require a much narrower range than the servo's own range. Settings save locally; commanded positions do not.

## Files

- `arm_controller.py`: the actual desktop app; uses the existing Python/serial environment.
- `settings.json`: created when you save joint limits and pulse calibration.
- `commands.log`: commands and board replies for troubleshooting.
- `installation.json`: installed image hash, backup location and checks performed.
- `window.stdout.log` / `window.stderr.log`: startup diagnostics.

Firmware source is `C:\LJWB03\project\apps\main\actuator_test.c`. The camera commands remain installed. Do not open the old component tester and arm controller together: they share GPIO12/GPIO10 and the serial port. Physical loaded performance is for the user to test after suitable power and clearance are established; installation verification intentionally issues no valid movement commands.
