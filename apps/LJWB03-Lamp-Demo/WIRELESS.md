# Wireless lamp control and updates

Wireless control was verified on the project board on 31 October 2026. Configure your own 2.4GHz network and pair each PC locally. The laptop and board can use different frequency bands if their networks permit local communication. Verification used the laptop on this same 2.4GHz network; cross-band routing has not been tested.

Open **Lamp Studio** as usual. It automatically uses Wi-Fi when Wireless setup has enabled it. Powering the board makes it join its saved Wi-Fi. Reconnection restores communications, not previous movement. Keep the board powered by USB or another appropriate board supply; disconnecting its sole power cable turns it off. Servos require their separate regulated supply/common ground.

## Setup and recovery

The **Wireless setup** button opens Wi-Fi configuration, USB pairing, wireless discovery and firmware upload. Disconnect Studio first so the setup window can use USB. On closing setup, Studio resumes automatic connection attempts. Choose **Use USB instead** to return to the wired controller.

For another Wi-Fi: attach USB data, disconnect Studio, enter the 2.4GHz network/password locally, and choose Save Wi-Fi via USB. Pair this PC via USB if necessary, then Find lamp & enable wireless. The board password persists on the board. The independent pairing key is kept in `%LOCALAPPDATA%\LJWB03\wireless.json`, outside the shared project. Do not publish that file. Pairing again replaces the previous key.

Discovery uses UDP45832 and control/update uses TCP8032. If discovery is blocked, the optional Board IP field can use the address shown by USB `net_setup status`. If the network blocks device-to-device traffic entirely, use a PC hotspot or another network. Use the address reported by your board; DHCP may change it. Discovery refreshes the address by device identity when possible.

## Firmware updates

Support the lamp, Release all, switch external servo power off and disconnect Studio. Open Wireless setup → Upload firmware over Wi-Fi. Select a compiled ESP32-S3 application `.bin` that retains wireless support, not a ZIP, model or merged full-flash backup. It uploads, verifies SHA256 and the ESP application format, selects the inactive application slot and restarts. Your Wi-Fi, pairing and models are preserved. Interrupted/invalid uploads do not select the incomplete image.

The firmware rejects updates while servo outputs are active. Original bootloader rollback is **not enabled**, so this is not a guarantee of automatic recovery from a valid but malfunctioning future application. Keep USB for recovery. After OTA, the active application can be ota_1 at0x410000; old USB installers that blindly write0x20000 may not update the running slot. Use this updater or inspect the active slot first.

This is a paired local-network HTTP service, not an internet-exposed remote-management service; do not forward its ports. Supported wireless commands are bounded arm_live commands, LED controls and selected audio controls. Network credentials, arbitrary CLI execution, camera captures and microphone exports are not exposed. Existing motion-renewal and hold-loss watchdogs remain active; communication loss can eventually release the lamp, so adequate mechanical support remains necessary.

## What this does not enable

LJYD voice conversation remains a separate integration. Wireless Studio still runs the choreography on the laptop and sends small movement targets to the board. This update does not install a speech model or make routines autonomous on the board. Settings/profiles are saved on the laptop as before.

Private device receipts are omitted. Paired discovery, status, invalid-request rejection and two same-image OTA cycles were verified on the project board; a later speaker-only chirp also completed over Wi-Fi. No physical movement was needed for those checks.
