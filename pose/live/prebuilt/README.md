# Historical camera/YOLO application

`wb03_live_pose.bin` is the application built on 30 October 2026 from the
camera stream restart fix. Size: 1,287,392 bytes. Verify it against
`SHA256SUMS.txt` before using it. It contains no device flash backup or NVS.

This is a separate camera/pose application. Installing it replaces the lamp
application; it does not add pose recognition to the lamp firmware.

The original compatible layout used an application at `0x20000` (`ota_0`,
capacity `0x3f0000`) and an already installed packed COCO Pose S3 V1 model at
`0x810000`, length 3,117,712 bytes, SHA-256:

```
1d7a70a5a120ae595d5de5c5ae17889739b1e30e67aec8511f9ef643d44e8585
```

Model weights, bootloader, partition-table binary, OTA data and NVS are not
bundled. Obtain model sources and licenses from the pinned Espressif source
described in `../../README.md`, and build/pack the exact S3 V1 model. A raw
model file and a packed flash model are not necessarily identical. A hash
mismatch is a reason to stop, not permission to overwrite the model.

Before any separately authorized installation, identify the actual board,
check flash/security settings, partition table and active OTA slot, create
and independently verify a recoverable backup, verify the complete installed
model, and define the recovery procedure for that board. Partition equality
alone does not prove the bootloader will select `ota_0`. Keep actuators
unpowered. Never apply a generic full-chip flash/erase command. No installer
is included because the original script depended on one private machine and
one previously checked board. Serial/esptool access may reset a board.

After an authorized application-only write, independently verify the written
application and check camera function and stop/port-release behavior. This
export/upload does not perform or authorize flashing.
