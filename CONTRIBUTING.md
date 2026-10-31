# Working together

Create a branch or fork and open a pull request. Explain what changed and whether it was tested in preview, with simulated hardware or on the actual lamp.

For motion changes, preserve500..2500µs position command bounds, the separate continuous-base behavior, Stop, output-release warnings and connection watchdogs. No auto engagement or motion resume on USB reconnect. Include software tests when changing timing, calibration or protocol behavior.

The public cardboard profile is a reference. Save assembly-specific profiles under a new name. Review changed calibration JSON before pushing; don't replace another person's profile accidentally. Firmware/software protocol changes must account for the SDK CLI's eight-token limit.

Keep Wi-Fi/product/device secrets local. Never commit `.env`, recordings, raw flash/NVS backups, logs with payloads, toolchain installations or build output. Public docs should describe repeatable steps rather than private machine paths.

Firmware needs the organizer-provided SDK. Read firmware/README.md before applying overlays or flashing. A passing software test does not establish collision-free movement or cloud integration.
