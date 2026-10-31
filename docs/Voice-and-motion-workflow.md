# How Hello Arm will work

This is the intended integrated behavior, not a claim that the current firmware already performs it.

1. You say “Hello.” The robot microphone captures the sound.
2. The board/audio module packages the sound and sends it over Wi-Fi and the internet to the configured cloud voice service.
3. Cloud speech recognition turns sound into words. The configured agent interprets the words and chooses a reply and, if configured, a device action.
4. Two kinds of information return to the robot: audio for the spoken reply, and structured commands for supported device actions.
5. The board plays the reply through its speaker. Our local firmware interprets an allowed action, such as “greet,” and runs the arm gesture with our motion limits, timing and stop/watchdog behavior.

The source's normal voice path uses Agora with Opus-compressed audio; its events include ASR text, agent text and TTS text. The device-control code separately parses JSON messages over the IoT/MQTT path. Speech is not simply a JSON file containing the whole audio recording. Exact service-internal recognition/reasoning/voice providers depend on platform configuration and were not established by the briefing excerpt.

Illustrative action only, NOT a confirmed LJYD message schema:

```json
{"action":"greet"}
```

We still need to define/map that action in LJYD and implement its corresponding device handler. The existing method table includes chat quit/resource playback, not a robot-greet action. Cloud should request a named supported action; the board owns the precise motor pulses and local bounds. A live voice reply and an arm gesture also need explicit coordination if the reply must wait for the movement to finish.

For the PC-hotspot arrangement:

Robot → PC hotspot → school internet → cloud services.

The laptop shares internet like a router. It does not ordinarily transcribe, reason about, or manually forward the cloud messages. The phone is optional for a future official pairing mini-program; it is not required for the current USB setup route.

Current installed firmware preserves local microphone/speaker testing and the arm demo, and adds explicit Wi-Fi/product authentication setup. It does not start the normal voice-agent path, BLE pairing or remote arm-action mapping. Initial registration requires the real product PID/secret and any required account binding; conversation/motion integration follows.

Three different credentials:

- Wi-Fi password: lets the board join YOUR_HOTSPOT. A protected hotspot requires at least8 normal ASCII characters. A short password cannot be made valid by removing a GUI check; the hotspot itself enforces its authentication rules.
- LJYD Product ID: identifies the cloud product.
- LJYD Product secret: authenticates that product's device-registration request. It goes in the product-secret field, not the Wi-Fi field.

The revised window keeps manually typed fields for retries, offers Show password, and makes password-free networks an explicit choice. “Use this PC hotspot” obtains the existing Windows hotspot settings and sends them to the board without printing or saving the password to PC logs. The board's saved Wi-Fi details survive restart; the PC hotspot must still be switched on and the laptop awake.
