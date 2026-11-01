# BF3901 startup ID validation

Apply `bf3901-stable-id.patch` to the prepared component root containing
`esp_cam_sensor/`, before building `pose/live/firmware`:

```sh
patch -p1 -d "$YOLO_COMPONENTS_DIR" < pose/live/firmware/patches/bf3901-stable-id.patch
```

Base: esp-video-components commit `ac5d2ac96d63f5222cff77d90a4409fb0c3b8c76`,
esp_cam_sensor 2.2.0. Apply once to a clean copy; do not stack with the temporary
`diagnostics/bf3901-id-samples.patch`.

On the connected WB03, the first ID read after wake-up was sometimes incorrect,
while the next nine reads were all 0x3901. Require three consecutive full matching
ID reads, with at most eight attempts and 20 ms between attempts. A failed read
or wrong ID resets the consecutive count. Never accept an alternate sensor ID.

Three actual restarts recovered first IDs 0x7c01, 0x3d01 and 0x1d01, each reaching
three consecutive 0x3901 reads on attempt four. This fixes premature detection
failure only: all three subsequent frame captures still timed out. Do not claim
camera streaming is fixed. Keep stock 100 kHz SCCB and combined transactions;
lower-clock and STOP-separated read experiments did not resolve the fault.

See `docs/LIVE-CAMERA-DEBUG-2026-10-31.md` for current device evidence and image identity.
