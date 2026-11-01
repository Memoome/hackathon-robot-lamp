# Lamp diagnostic firmware

**Branch source update (1 November):** new builds of the offline-audio lamp application now automatically apply the packaged Rest targets at boot and hold them. This includes software/OTA reboots. Initial position is unknown, so first engagement is direct PWM, not guaranteed smooth motion. Existing prebuilt binaries do not contain this change. See `docs/PROJECT-STATE.md` for ownership, tests and deployment limits. Regenerate `boot_rest_target.h` using `python3 tools/export_boot_rest.py` from the repository root after changing `actions/return_rest.action.json`.

`overlay/` contains project application changes relative to the organizer's WB03 SDK root (with apps/ and qumios-dev/). Obtain that compatible SDK and ESP-IDF 5.4.1 separately. This overlay is not a standalone SDK distribution.

Apply to a separate working copy:

```powershell
.\Apply-Overlay.ps1 -VendorSdkRoot C:\WB03SDK
idf.py -C C:\WB03SDK\apps -B build-lamp -DOFFLINE_AUDIO_TEST=ON build
```

The vendor SDK may need its original dependency/configuration setup. A clean build on another teammate's machine has not been verified. Public `ljyd_cloud.h` has empty product identity: configure your own locally for product builds, and do not commit secrets. Diagnostic setup can save a separate runtime identity. Diagnostic mode does not start normal LJYD conversation.

## Application images

- **lamp-action-lights.bin**: current ten-sound application with wireless/OTA, LEDs, chuckle and closing stretch ahhh. Check action-lights-manifest.json.
- **lamp-wireless.bin**: earlier eight-sound wireless build, insufficient for all current actions.
- **lamp-led.bin** and **lamp-demo.bin**: historical recovery references that predate wireless; do not use them expecting Wi-Fi to remain available.

These files are application-only, not full-flash backups. Models, NVS, bootloader and partition table are separate. The current application's USB installation was verified on the project board; that does not validate all physical gestures or a fresh SDK build.

## Updates

Support the lamp, release outputs, switch external servo power off, disconnect Studio, then use **Wireless setup → Upload firmware over Wi-Fi**. Choose an application image retaining wireless support. The updater writes the inactive slot, checks SHA256/application format, and restarts; it refuses active servo outputs. Keep the board powered throughout. Invalid/incomplete uploads are not selected. Automatic rollback for a valid but malfunctioning future application is not enabled; USB recovery may be needed.

After OTA the active slot can be ota_1 at0x410000 instead of ota_0 at0x20000. **Do not blindly use an old fixed-offset USB installer.** Inspect the actual board/security/partition/active-slot state, back up its application and preserve settings/models before any USB recovery. Nothing here automatically flashes hardware.

See apps/LJWB03-Lamp-Demo/WIRELESS.md for local pairing and discovery. The service uses paired local HTTP, not TLS; keep it on a trusted LAN without port forwarding. Local pairing keys and actual board/network addresses are excluded from this repository.
