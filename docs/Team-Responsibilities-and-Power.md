# Team responsibilities and hardware direction — 28 October 2026

Fresh check: board Wi-Fi Online, product11823 and identity present. Cloud NOT online. A retry reported `dynreg failed ret=0 did=0`: no device ID was obtained. This does not prove which credential/environment/account condition caused failure. Redacted evidence: cloud-registration-check.json. Former GUI “Connecting / awaiting registration” represented a requested attempt, not successful authentication. The host UI wording has been corrected; no firmware change for that label.

## Responsibility split

| Hardware/firmware team (Arnav and Percy) | Software/cloud team | Shared agreement |
|---|---|---|
| Mechanics, servo mapping, power, wiring, sensors/camera/lights, calibration and tested local gestures. Firmware networking/audio integration, command parsing, limits, watchdogs, stop and result reporting. | Agent personality, conversational/model settings, platform product/agent binding, thing-model/action configuration, intent-to-action mapping and any app/dashboard. | Named commands and parameters, reply format, busy/error/completion reporting, timing of speech vs motion, and test cases. |

Firmware is software running on the ESP32. It is the local executor between cloud commands and physical hardware; an extra laptop server is not inherently required. Appoint one platform owner so hardware and software teams do not duplicate account configuration. Hardware work and platform configuration can proceed in parallel.

Preferred first action contract: greet, happy_dance, stop. These are proposed names, not already-enabled LJYD commands. The cloud requests a supported behavior. The local firmware stores/executes its choreography and checks bounds. Low-level angle commands are possible if deliberately designed, but do not assume LJYD knows our arm geometry, pulse calibration, collision limits or choreography. Existing manual/Hello demo code is reusable, but a cloud action-to-gesture bridge and voice integration are still required.

## Power and construction

Use external regulated servo power for the four-servo arm, sized for combined worst-case/stall current plus margin. Keep signal wires on board GPIOs12/10/11/15 and connect servo ground to board ground. During development, power the ESP32 by USB and servo positive supply separately. Do not join external+5V to the USB-powered board's5V unless its power-input/backfeed arrangement has been checked. Do not feed the7.4V battery output directly to SG90/MG90S-class servos without confirming that exact model's voltage rating.

Lowest disruption: external supply plus a suitable power-distribution block/servo connector board, retaining current GPIO servo signals. This requires no servo-protocol rewrite. Use connectors and power conductors rated for the combined current.

Optional PCA9685 I2C servo-driver breakout: provides convenient servo signal outputs/connectors and a separate V+ servo-power rail; it still needs an external servo supply. For ESP32, use3.3V logic/VCC and appropriate servo V+; check actual breakout design. It requires firmware changes and bus/pin planning alongside the camera. It does not connect a camera or directly drive arbitrary LED strips/high-power lamps.

The camera keeps its existing3.3V interface/wiring. The correct lighting driver depends on the light: indicator LED/resistor, addressable LED data connection, or suitable MOSFET/constant-current driver for higher-power lighting. A single universal servo/light/camera board should not be assumed compatible.

Prefer modular connectors/distribution now; solder a small carrier/perfboard after the pinout and power arrangement have been tested. Keep3.3V/5V rails distinct, insulate joints and give moving cables strain relief.

Primary reference: https://learn.adafruit.com/16-channel-pwm-servo-driver/pinouts and https://learn.adafruit.com/16-channel-pwm-servo-driver/hooking-it-up . No exact supply current requirement for these particular servo clones has been measured.
