# Component tester

Double-click **Test Components.lnk** in Desktop\Hackathon-ESP32S3. Do not paste a launcher's contents into PowerShell.

1. Wait for **Board ready**.
2. Check VCC power, common ground, and that the servo arms have free space. Tick the wiring checkbox.
3. Press Left, Center, or Right on either servo card. Each signal lasts 0.5 seconds, then releases.
4. Set the vibration strength and press **Vibrate 0.25s**. Start at 100% for the first short test; lower settings may not start the motor.
5. **STOP / release all** turns the signals off. Closing the window also sends Stop.

## Wiring

- **MG90S position servo signal → GPIO12**.
- **SG90 position servo signal → GPIO10**.
- **Vibration module IN → GPIO13**.
- Suitable **5V power → VCC/power**; connect all grounds to board ground.
- GPIO connections are control signals, not a power supply for motors. The user confirmed the vibration part is a three-pin VCC/GND/IN module with a driver, rather than a bare motor.

The vibration PDF in Hardware-Documents describes active-high input, a 3.0–5.3V working supply, MOSFET drive, and PWM support. The interface uses 1kHz PWM for the module. Servos use 50Hz PWM with conservative 1300/1500/1700µs test positions. The labels do not claim calibrated angles.

Only one component is driven at a time. Firmware independently releases servo signals within 600ms and motor signals within 500ms even if the laptop app closes or disconnects. There is no automatic movement, vibration, microphone recording, or playback at startup. Releasing a servo signal removes commanded holding torque; it does not return the arm to center.

The existing microphone commands remain available. Close this tester before using the microphone tester or another serial monitor, because the component window owns the USB serial connection while connected.

## Firmware and recovery

Source: C:\LJWB03\project\apps\main\actuator_test.c and actuator_test.h. The diagnostic startup registers the new act_test commands; the product startup path remains unchanged. Rebuild with C:\LJWB03\Build.ps1 -Mode Diagnostic. Building alone does not upload.

The installation records are in installation.json and C:\LJWB03\pc-setup-results. The preceding application partition is backed up there. Original full-board backups and the frozen revision-3 diagnostic image remain in the kit.

Source reference: <USER_HOME>\Desktop\Hackathon-ESP32S3\Hardware-Documents\震动马达.pdf. Driver reference: https://docs.espressif.com/projects/esp-idf/en/v5.4.1/esp32s3/api-reference/peripherals/ledc.html
