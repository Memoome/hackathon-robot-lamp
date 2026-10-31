# Camera tester

Open **Test Camera.lnk** in Desktop\Hackathon-ESP32S3.

1. Wait for **Camera detected**. This checks the board and camera; the window does not take a photo at launch.
2. Aim the camera and click **Capture photo**.
3. Wait while the board captures and downloads a frame, usually about 10 seconds.
4. The photo appears in the window and is saved automatically. **Save a copy...** lets you choose another location; **Open saved photos** opens the current take's folder.
5. **Cancel** cancels an in-progress capture. Close the window after the operation ends.

This first version is a one-shot USB camera preview, not continuous video. The sensor uses 240×320 UYVY; the board produces a 120×160 preview for a shorter USB transfer. The window enlarges it for viewing. Each take saves the original transferred UYVY frame, a decoded PNG, metadata, and the raw transfer log. Sequential offsets, exact byte count, and the board's FNV32 checksum are checked before any photo is displayed.

Close other serial monitors and the component tester before connecting. The camera tester opens the serial port only during a check or capture.

## Wiring used

Camera adapter VCC=3.3V, GND=GND, SDA=21, SCL=47, VSYNC=4, **PCLK=9**, D0=8, PWDN=41. HREF/D1 are unused. The adapter has its own clock, so the firmware does not drive an external XCLK or touch the vibration module's PWM timer. GPIO13 remains the motor-module IN; GPIO12/GPIO10 remain the servos. Pins 8 and 9 cannot simultaneously be used for the optional MPU6050.

Disconnect power before changing wiring. Match the adapter's printed labels; the supplied PCB header drawing is a back-side view. See the desktop Guides/Camera-Wiring folder.

## Troubleshooting

If Camera not detected appears, check 3.3V, ground, SDA/SCL and PWDN, plus the camera ribbon. If detection succeeds but capture times out, check VSYNC, PCLK→GPIO9 and D0. Short wiring helps the fast camera clock. No partial or synthetic image is substituted on failure; the previous photo remains visible.

The microphone and bounded actuator commands remain in the diagnostic firmware. Camera status does not prove those other peripherals are healthy. installation.json records the observed audio-module status separately.

Firmware: C:\LJWB03\project\apps\main\camera_test.c/.h. Camera I/O is initialized on a requested probe/capture. Capturing stops streaming before USB export; no continuous background capture is started by the window. The user's existing app is backed up before the app-only update; the bootloader, partitions, settings and models are not flashed.
