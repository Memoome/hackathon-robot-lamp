# Current base update

Base is now **SG90 position servo → GPIO15**, replacing the continuous MG90S. Use Lamp Studio's Rotating base top-down position controls. Old continuous-speed/timed-turn controls are disabled in Studio. Existing firmware supports this. All three bending-joint assignments remain unchanged. The historical notes below describe the previous base where marked continuous.

# Actual lamp servo update — 31 October 2026

| Part | Servo | Signal | Mode |
|---|---|---|---|
| Lift / joint 1 | MG996R | GPIO12 | Position |
| Elbow / joint 2 | MG90S | GPIO10 | Position |
| Head / joint 3 | SG90 | GPIO11 | Position |
| Rotating base | MG90S, current 360° version | GPIO15 | Continuous speed/direction |

The installed firmware already sends 50Hz servo pulses, with 500–2500µs command capability. No firmware replacement, automatic movement, pulse rescaling or calibration reset is needed just to communicate with these motors. The continuous base retains its existing nominal 1500µs stop and speed controls.

The previous calibration belongs to the cardboard prototype. Servo replacement, horn mounting and the new structure can change the real angle at any pulse. Keep the saved prototype profile, adjust the observed model for the actual lamp, and save a separate profile. Recheck checkpoints and routines before running them. The visual 180° sector is a model assumption, not a measured guarantee.

For the new MG996R, initially test unloaded or with the lamp supported near 1500µs; explore 1000–2000µs first. Expand in small steps only with free travel. Do not assume 500 and 2500µs are valid physical endpoints for your particular unit. Those full software controls remain accessible as requested.

TowerPro's [MG996R product page](https://towerpro.com.tw/product/mg996r/) specifies 4.8–6.6V, 1.4A stall current and 170mA no-load operating current, but no guaranteed pulse limits. Its manufacturer response also gives 159° travel for that product, so the model name alone does not establish 180° travel. The [MG90S page](https://towerpro.com.tw/product/mg90s-3/) likewise does not establish the pulse-to-angle map of this particular servo. Check the supplier specification and observed travel of the purchased units.

Use regulated external 5V for the servo red wires. Join every servo ground to supply ground and board GND. Keep external +5V separate from the USB-powered board's +5V rail. The larger lift motor adds substantial current demand; a supply adequate for the old micro servos may drop voltage under this load. Battery mAh describes capacity, not available output current. Do not route the MG996R's power through a board GPIO or the board's 3.3V supply.

A future 180° base servo requires a position-control mode and angle calibration; do not simply swap it into the current speed-control interface.

Lamp Studio now shows the updated motor names and a **Servo wiring** button. Reopen it to load the interface update. No physical movement or loaded power test was performed for this change.
