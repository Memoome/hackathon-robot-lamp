# Third-party material and provenance

- ESP-IDF5.4.1, Espressif ESP-DL (pinned revision in pose/README.md), COCO Pose0.4.1 and their dependencies are obtained from Espressif. Retain their licenses when downloading or distributing them.
- WB03/QuMios/LJYD source overlay files derive from or integrate with the hackathon-provided SDK. Original notices and upstream ownership remain; obtain the full SDK from the organizers. Proprietary precompiled vendor libraries and the portable toolchain are not bundled here.
- `offline_music.pcm`: Carefree by Kevin MacLeod, CC BY4.0, excerpted/converted/level-reduced/faded. Attribution and source/license links are alongside the asset at firmware/overlay/apps/main/offline_music_attribution.txt.
- Lamp robot and musical gesture cues were synthesized locally. The Hello sample was generated locally using Windows speech synthesis. They are not movie samples.
- Hardware PDFs and the prototype STL are provided project reference material and retain their original authorship. Consult the original manufacturers and supplied documentation for specifications.
- Python requires pyserial; Windows Tkinter and winsound are used by the desktop tools.
- `pose/live/firmware/main` and its historical prebuilt application come from the team's BF3901/YOLO integration, using ESP-IDF5.4.1, ESP-DL3.3.14, COCO Pose0.4.1 and Espressif video/sensor2.2.0 components. Their original notices and licensing obligations remain applicable. The ESP-DL source revision and camera component manifest revision are recorded in `pose/live/README.md`. Third-party SDK/component sources and model weights are not redistributed in this addition. The prebuilt image is separate from the lamp application.
- `pose/live/host/posture.py` is the team's experimental geometry/baseline implementation. Design references were `https://github.com/aaron888hacker/-yolov8-` and `https://github.com/Yoadkk/postureGuard`; no code or weights were copied from them. These references do not validate the thresholds or medical accuracy.

No blanket license is asserted over third-party SDK code or hardware documentation. Team contributions should retain upstream notices.
