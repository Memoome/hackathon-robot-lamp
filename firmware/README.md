# Lamp diagnostic firmware

`overlay/` mirrors selected paths relative to the organizer's WB03 SDK root (the directory containing apps/ and qumios-dev/). It includes application motion/camera/audio/network additions, main/CMake integration, audio assets and the VB701N driver changes needed by our diagnostic. It is **not a standalone replacement for the full vendor SDK**.

Use the organizer-provided SDK and compatible ESP-IDF5.4.1 environment. Apply to a separate working copy:

```powershell
.\Apply-Overlay.ps1 -VendorSdkRoot C:\WB03SDK
# From an activated ESP-IDF shell:
idf.py -C C:\WB03SDK\apps -B build-lamp -DOFFLINE_AUDIO_TEST=ON build
```

The SDK may require its existing config/dependency setup and original component assets. The overlay was exported from the working original SDK; a fresh vendor distribution/build on a teammate's machine has not been tested. Do not replace vendor-managed dependency versions indiscriminately. The diagnostic deliberately uses runtime USB-entered identity rather than source sample product credentials.

`prebuilt/lamp-demo.bin` is the verified application image only. Do not run generic full-flash commands from build logs over an already configured board. A safe installation must verify the exact board/security/partition table, back up its current application, preserve NVS/models, write only the application at0x20000 in the matching reference layout, verify the digest, then confirm outputs off and audio status. Other boards/layouts require a different procedure. Application download alone does not save board credentials or restore a changed model partition.

Do not flash while the unsupported lamp can fall: support it, turn external servo power off and close controllers first. No installer in this repository automatically flashes the board.
