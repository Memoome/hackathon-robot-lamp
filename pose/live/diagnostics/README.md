# Local signal diagnostics, 31 October 2026

These patches preserve the temporary measurements used to diagnose the GPIO4
VSYNC/SPI-CS problem. They are not required by the final minimal fix in
`../firmware/main/camera_main.c`, and they are not included in the repository's
historical prebuilt image.

- `esp-camera-2.2.0-raw-diagnostics.patch`: apply to a separate copy of Espressif
  esp-video-components commit `ac5d2ac96d63f5222cff77d90a4409fb0c3b8c76`.
  It collects bounded callback/header samples and reports decoder failures.
  **Do not interpret `trans_len=0` as no physical data:** the same zero value
  was observed on successful complete frames. Samples from unfilled buffers
  may contain old memory rather than sensor bytes.
- `live-pin-counters.patch`: apply to a separate copy of `pose/live/firmware`
  from `cc83479`, not on top of the final minimal fix. Adds temporary PCNT
  measurements and GPIO4 input filtering. The two GPIO4 PCNT counters use
  no filter and a 1,000 ns filter respectively. This PCNT filter affects only
  measurement; the separate GPIO pin filter affects the actual SPI input and
  uses the ESP32-S3's fixed two-IO-MUX-clock window. GPIO9/8 counts are activity
  evidence, not calibrated high-frequency measurements. PCNT temporarily
  enables a pull-up when channels are created; the helper immediately disables
  it and the pull-down before measurement.

Retain all original frame-header, line-header, size and checksum checks.
Do not run generic full-chip flash commands. The final application was built
without these patches, with only GPIO4 pin filtering added; three consecutive
capture/transfer/inference cycles passed on the connected board.

Detailed evidence, build versions, private local backup location and current
installed-image identity are in `../../../docs/LIVE-CAMERA-DEBUG-2026-10-31.md`.
No private captures, raw device backup, model weights or vendor SDK are added
to Git by these patches.
