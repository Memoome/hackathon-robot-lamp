# LJYD hackathon platform briefing — 28 October 2026

Source: user-supplied Chinese transcript titled 灵机一动智能体平台专项讲解直播, labelled 2026/10/28 15:51. This is a summary of that excerpt, not a complete recording review. The pasted text ends as the embedded engineer's demonstration is introduced. It contains neither that demonstration nor the promised Q&A.

## Main findings

- LJYD is the cloud platform for creating/configuring agents and connecting them to hardware products. It does not implement custom physical hardware functions for us.
- Agent configuration and actual device operation are separate things to test. A successful browser conversation does not prove that the physical robot works.
- Build one core interaction first rather than adding many plugins.
- The correct development selection for the supplied board is **SDK 集成 (SDK integration) → WB03**.
- The product's **身份凭证 (identity credentials)** include its **PID** and **产品密钥 (product secret)**. The speaker explicitly says these are used for device firmware setup. This confirms that the PID/secret registration route in the supplied SDK is intentional.
- There is a mini-program pairing/control-panel flow. Its exact mini-program name, QR code, permissions, account-binding process and actual pairing sequence are not provided in this excerpt.

## Speaker viewpoints

Although every transcript line is labelled 李金龙, the introductions identify different roles. Attribution below follows those introductions; names/spellings may be transcription artifacts.

**Host, introduced as Hani:** the session prepares Saturday's hackathon participants. It is meant to cover platform/agent creation, an embedded-device demonstration, and a development-team Q&A. Only the introduction and platform presentation appear in the supplied excerpt.

**Product manager, introduced as Baiyi (柏一/百一):** start from the product's audience, role and core task. Configure an agent's instructions, conversational models, opening/closing messages and necessary capabilities. Available plugin examples include Moji weather, resource playback, alarms and location. AI-assisted creation can generate a draft from a natural-language product description, but the team must review, test and refine it. Use the product-development workflow to link the agent and hardware.

**Embedded engineer Su Hang (苏杭):** introduced to demonstrate the hardware. No substantive demonstration or instructions from this speaker are included in the pasted excerpt.

## Platform workflow described in the presentation

1. Create an agent: name, role, task and related basic information.
2. Configure conversational/voice model settings, opening and closing messages, and only the capabilities needed for the initial use case.
3. Test it using browser voice conversation; revise settings if the behavior is wrong.
4. Enter **产品开发 (Product development)** and create a product with a suitable category and basic information.
5. Review its **物模型 (thing model)**: the properties/actions/events used to describe what the device can do. Categories provide default capabilities; add custom capabilities where needed. Adding a capability in the platform still requires matching device implementation.
6. In **智能体绑定 (Agent binding)**, bind the agent created above.
7. In **设备开发 (Device development)**, select **SDK 集成 → WB03**.
8. Configure pairing instructions/image and the control panel. The platform supports a mini-program preview and custom panel uploads. These visual customizations are not the actual motor-control firmware.
9. Return to the product-information page and inspect **身份凭证** for **PID + 产品密钥**.
10. Configure the actual device with that product identity and test the physical device end to end.

The presenter verbally numbers parts of the product workflow inconsistently. The labels and sequence above preserve the substantive steps rather than treating the spoken count as exact.

## Implications for Hello Arm

**Hello Arm is still a proposed initial name, not a confirmed created LJYD product.** Browser control failed in earlier attempts; no product credentials were retrieved or installed.

Our desired split is:

- **LJYD:** agent role, model/capability configuration, conversation and configured device actions.
- **Board firmware:** microphone/speaker operation, networking and authentication, interpretation of supported actions, motor timing/limits/watchdogs and peripheral handling.
- **Laptop:** development, initial setup and the optional school-Wi-Fi hotspot. It is not inherently a required cloud-message relay.

Last verified networking on 27 October: board joined the PC's 2.4 GHz hotspot **YOUR_HOTSPOT**, with the laptop sharing **YOUR_UPSTREAM_WIFI**. Board IP was **192.168.137.23**; it may change. This is historical connection evidence, not a fresh check on 28 October. Keep the PC awake and its hotspot on when using this arrangement.

The current installed custom diagnostic preserves the arm demo and supports USB commands for saving Wi-Fi and team product identity, then explicitly starting LJYD registration. It does **not** start the normal product BLE-provisioning function or voice-agent path. Therefore a phone mini-program should not be expected to discover/pair with this firmware yet.

Two routes are available:

1. **Initial cloud registration using our existing setup window:** obtain the correct team's product PID/secret and server environment; save those in Wi-Fi and LJYD Setup, then Connect to LJYD and verify Online plus appearance in the correct platform account. Platform device/account binding may still be a separate requirement.
2. **Official phone mini-program pairing:** obtain the organizers' official mini-program name/QR and WB03 demonstration instructions; integrate/enable the compatible product provisioning flow while preserving the arm controller and handling ownership of the audio module. Then pair using the PC hotspot's Wi-Fi details. Exact WeChat UI steps remain unverified.

The talk's “hold for 3 seconds” line was an example of text entered into the pairing-instructions panel. It is not proof of which physical button to hold on our custom firmware. The product source has a GPIO14 reset/unbind behavior, while our diagnostic skips its initialization. Do not use an assumed long-press as a universal pairing procedure or reset a working network unnecessarily.

## To-dos

- **Percy / platform operator:** create the minimal Hello Arm agent and product; bind them; choose SDK integration and WB03; retrieve PID/secret privately; confirm production/test environment and account/device binding requirements.
- **User / organizers:** obtain the official mini-program name or QR and the missing embedded-device demonstration/Q&A, especially the device pairing procedure.
- **Agent / firmware work:** verify initial registration using the real product identity; add BLE provisioning only if the mini-program route is wanted; integrate microphone/speaker ownership and the cloud voice-agent path; preserve the working arm demo.
- **Team:** validate browser conversation separately from real-device voice; then map a single supported action such as greeting to our bounded local gesture and test interruptions/reconnection.

## Still unknown

The excerpt does not establish exact ASR/TTS providers or model names, availability/price/quotas, whether custom actions need product publication/approval, how account binding works, whether a product must be published before pairing, or the exact mini-program identity. Do not present these as confirmed meeting facts.
