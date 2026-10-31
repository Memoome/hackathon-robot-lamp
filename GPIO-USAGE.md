# Lamp GPIO reference

Updated 31 October 2026. This is the current project's wiring map, not a list of every pin available on the chip. Numbers below are GPIO labels, not connector positions. Keep this file updated whenever hardware assignments change.

| GPIO | Use | Direction from ESP32 | Hardware / notes |
|---|---|---|---|
| **1** | LED ring DI | Output, WS2812 data | **8 LEDs** confirmed by user. External regulated 5V. DO unused unless chaining another ring. Studio LED controls require the lamp_led firmware addition. |
| **12** | Lift / joint 1 | Output, 50Hz servo | MG996R position servo. |
| **10** | Elbow / joint 2 | Output, 50Hz servo | MG90S position servo. |
| **11** | Lamp-head tilt / joint 3 | Output, 50Hz servo | SG90 position servo. Previously called end plate. |
| **15** | Rotating base | Output, 50Hz servo | MG90S continuous rotation. Pulse controls speed/direction, not angle; nominal stop1500µs. Future180° servo requires a different control mode. |
| **21** | Camera SDA | Bidirectional, I2C | BF3901 adapter control data. |
| **47** | Camera SCL | Output, I2C clock | BF3901 adapter control clock. |
| **4** | Camera VSYNC | Input | Driver treats this as frame/CS signal. Do not enable old single-servo GPIO4 example. |
| **9** | Camera PCLK | Input | Successful camera wiring uses9, not13. |
| **8** | Camera D0 | Input | One-bit camera data. |
| **41** | Camera PWDN | Output | Camera power-down control; operating level low. |
| **40** | Audio UART TX | Output | ESP32 → VB701N audio module. Built-in connection. |
| **39** | Audio UART RX | Input | VB701N → ESP32. Built-in connection. |
| **38** | Audio flow/status | Input | VB701N flow control. Built-in connection. |
| **13** | Earlier vibration-module IN | Output, PWM | Reserved by actuator diagnostic; user previously removed this peripheral. Not a servo or camera pin. Do not connect a bare motor here. |
| **14** | Product reset/unbind button | Input with pull-up | Normal-product BSP assignment. Diagnostic mode skips that product provisioning path. Avoid reuse. |
| **43 / 44** | UART0 console TX / RX | Output / input | Standard ESP32-S3 default UART0 pins; project console115200. Keep available for board serial/programming wiring. |

## Power and LED wiring

- All external grounds join **board GND**. GND and5V are power connections, not GPIOs.
- Servo red wires and LED ring VCC use a suitable **external regulated5V** supply. Keep that external positive rail separate from the USB-powered board's positive5V rail.
- Camera VCC is **3.3V**, never5V.
- Recommended LED data path: GPIO1 → suitable3.3V-to-5V logic buffer (e.g.74AHCT125) →330Ω series resistor near ring →DI. Direct3.3V signalling is not guaranteed for a5V ring. DO is left unconnected for this single ring.
- A capacitor across the ring's5V/GND helps with transients; observe capacitor polarity. Use short ground/data wiring.
- At full-white maximum brightness, allow a conservative budget of about0.48A for8 traditional WS2812 LEDs, in addition to servo/board demand. Actual LED revisions differ; start at low brightness. Supply mAh is not its current-output rating.

## Conflicts and unused connections

- **MPU6050 is not assigned in this lamp.** Its old default SDA8/SCL9 conflicts with the camera. Remap it and update this table before enabling it.
- Old generic BSP examples use servoGPIO4 and vibrationGPIO5. They are not the lamp wiring; GPIO4 conflicts with cameraVSYNC. The current lamp uses servo12/10/11/15 and historical diagnostic vibration13.
- Camera HREF andD1 stay unconnected in the successful one-bit setup. Adapter has its own24MHz oscillator; no extra XCLK wire.
- GPIO0/3/45/46 have ESP32-S3 boot-strapping roles. Do not casually attach peripherals that force their boot levels. GPIO19/20 are native USB pins when native USB is used. Flash/PSRAM pins, including octal-memory reservations, must remain reserved according to this board's schematic; this table does not declare unlisted GPIOs free.
- LED controls are independent of servo calibration. The locked **final draft** snapshot must not be changed for LED work.

## Sources and implementation status

Camera: successful camera capture record plus main/peripheral/bsp_camera.h. Servos/vibration: main/actuator_test.c and user-confirmed replacements. Audio: main/qm_config/qm_config.h. LED: main/peripheral/bsp_ws2812.h (GPIO1,8LEDs), user confirmation, new main/lamp_led.c. Console: apps/sdkconfig. Product button: main/peripheral/bsp_io.c.

The LED firmware addition registers `lamp_led status`, `lamp_led set R G B` and `lamp_led off` in diagnostic mode. Registration/status do not drive the ring; first explicit Set/Off initializes it. Each channel is0..255. Studio scales selected RGB by brightness before sending. No light replay on application connect. LEDs retain their last colour if only USB communication is removed; turn them off explicitly before disconnecting if desired. Firmware build success and physical installation/light testing are separate checks.
