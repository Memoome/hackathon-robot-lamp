# Current shared project state ·31 October 2026

Main controller: apps/LJWB03-Lamp-Demo/visual_control.py. Latest behavior and limitations are in README.md and the main app guide. GPIO-USAGE.md is the full current wiring reference. Lift12=MG996R, elbow10=MG90S, head11=SG90, base15=continuousMG90S, ring1=8WS2812 LEDs. Camera/audio assignments retained.

The final draft profile preserves user-confirmed calibration; loaded copies are editable without overwriting that reference. Smooth large Slump/Water/Stretch routines use the same bounded quintic sampler in preview and hardware. Their timing is about8/13/13seconds fromRest. Original robot and music cues are retained.

Newest diagnostic image is firmware/prebuilt/lamp-led.bin, SHA256728cc848746dd98d6c85bd501b7221b633f99bd763be632326ab66fef6d9d967. Application-only installation and inactive servo outputs, audio READY/eight sounds, camera status and non-driving LED status/invalid-command rejection were verified. Physical LED output/loaded large routines were not exercised by the agent. The earlier prebuilt lamp-demo.bin remains a recovery reference.

Wi-Fi setup is implemented; a working LJYD live voice/action bridge is not established by this diagnostic. Agent/product binding, cloud authentication, live audio testing, action mapping and concurrent pose integration remain separate verification steps. The supplied application source includes voice and plugin integration work; code availability is not proof that the device currently runs it.

The portable source export excludes credentials, private captures/history, full flash backups, installed tools and the complete vendor SDK. SDK overlay builds still require the organizer's compatible SDK and dependencies.
