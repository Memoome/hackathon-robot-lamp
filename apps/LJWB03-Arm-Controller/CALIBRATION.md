# Calibrate the assembled arm

The **Arm Control** shortcut now opens `calibration.py`. The earlier generic angle controller remains in `arm_controller.py` as the shared serial transport and legacy UI; use the new window for this arm. Calibration changes require no new firmware.

Confirmed mapping: **bottom lift MG90S → GPIO12; middle SG90 → GPIO10; end-plate SG90 → GPIO11**. Camera wiring is unchanged.

## Before moving

You reported aggressive movement, little apparent reverse movement, and all three servos powered from board 5V. Those symptoms do not establish a software-only fault. The earlier controller released signals after 0.7 seconds in board-power mode; a loaded joint can then sag instead of holding its last command. The board 5V current capacity is unverified. Power, insufficient torque, binding, a loose horn, or servo type can also affect movement. Do not widen endpoints to overcome these problems.

**For your present power setup, disconnect the other two servo red wires and unload/support the tested joint.** Do not calibrate a loaded three-servo arm on unverified board power. For normal operation that holds all joints, use a suitable regulated separate servo supply, ground shared with board GND. Keep its +5V separate from board +5V while the board is USB-powered. No software library can increase available power or motor torque.

Close the old arm controller and other serial monitors before clicking **Connect** in the new window. Support the arm before closing a window that is holding it. The new window does not connect, engage, sweep or move automatically.

## Calibrate one joint

1. In **Find joint travel**, choose Bottom lift, Middle joint, or End plate. Verify only that servo is powered for the board-only bench test.
2. Select the actual power mode and confirm the wiring checkbox. Start with the arm unloaded. For initial setup, remove/loosen the horn or linkage if a centre command could cause contact; engage the bare servo, then align the linkage with power disconnected. Do not force a powered servo by hand.
3. The suggested initial pulse is **1500µs**. It is not a known safe physical pose. Click **Engage selected joint…** and confirm only when the initial move is clear. Without position feedback, the software cannot know the starting shaft position or guarantee a gentle first engagement.
4. Use **− pulse / + pulse** at **5µs per click** initially. You can type any positive whole-number increment into **Pulse step (µs)**, including 500 or 800. Moves clamp at the active exploration limits and never exceed 500–2500µs; for example, 2200 + 800 stops at 2500 with wider exploration enabled. Watch what actually happens. Use 2µs for fine adjustment; tiny steps may need several clicks before visible motion because servo deadband varies. Holding the mouse does not repeat it.
5. Initial exploration is limited to **1300–1700µs**. If the joint moves cleanly with clearance, explicitly unlock wider exploration and expand gradually. Absolute software bounds 500–2500µs are not a promise that the servo or linkage safely accepts that entire range.
6. Choose a usable lower/direction-A pose BEFORE any collision or strain, then click **Mark DOWN end · 0%**. Jog to the other usable pose and click **Mark UP end · 100%**. These labels define your desired directions. If UP needs a smaller pulse, save it that way; the arrows automatically reverse.
7. Jog to a convenient pose between those endpoints, then click **Save starting pose**. The three values save in `joint-calibration.json`. Marking/saving never sends a movement.
8. Repeat for each joint, moving its power connection only with power off. Check clearance with the other joints in different poses: independently marked limits do not guarantee that every combined arm pose is collision-free.

Do not hunt for the servo's hard mechanical stop. Mark useful arm travel with a margin. If the joint buzzes, bends the cardboard, cannot lift, or the board resets, stop and fix the load/power/mechanical problem first. If the servo keeps spinning at a fixed command instead of settling at a position, stop and identify whether it is a continuous-rotation variant; it cannot use position calibration in this window.

## Use the calibrated controls

Open **Move calibrated joints**. **Engage saved pose…** explicitly engages a joint at the saved pose after a warning. Then use its ↑/↓ buttons; start at **1% travel per click**. The progress bar and remaining travel refer to your marked endpoints, not an assumed 180° shaft range. A joint at 40% has 40% remaining toward DOWN and 60% toward UP.

In the board-only brief mode, the signal releases after 0.7 seconds. Support the joint; it may sag, so the display remains only the last command. Only one joint reference is kept when you engage another in this mode. For a working arm, separately powered hold mode keeps initialized joints holding while you adjust another.

Support the arm before **RELEASE ALL**, closing, disconnecting or removing power. Signals also release after about five seconds without host communication. Release is not a mechanical brake or electrical power disconnect. A position servo contains its own controller but does not send its actual position back through this three-wire connection.

## What was changed and checked

The new window offers direct pulse jogging, observed direction/endpoints, saved start poses, automatic arrow-direction mapping, travel percentages and cautious initial exploration bounds. It uses the installed `arm_test` CLI to request exact pulse widths; the internal protocol's 0/180 endpoint selectors are transport values, not physical angles. No firmware replacement or automatic movement was performed for this update.

Tests cover all integer pulse commands from 500 through 2500µs on all three GPIOs against the installed firmware's mapping formula, both joint directions, endpoint clamping, invalid-profile rejection, no movement on launch or save, and window layout. The earlier controller's four checks also pass. **This validates the software; physical endpoint calibration still requires your observations.**

## Useful references

- [ESP32Servo on GitHub](https://github.com/madhephaestus/ESP32Servo): supports direct pulse commands and configurable bounds. Its read methods return the last written command, not measured shaft feedback. Its default endpoints cannot determine your linkage clearance.
- [Arduino servo-motor guide source](https://github.com/arduino/docs-content/blob/main/content/learn/04.electronics/05.servo-motors/servo-motors.md): explains power requirements and an external servo supply.

Replacing your existing ESP-IDF camera application with a generic Arduino sweep example would discard the current setup and still require arm-specific calibration. We kept the installed board/camera firmware and changed the host controls.
