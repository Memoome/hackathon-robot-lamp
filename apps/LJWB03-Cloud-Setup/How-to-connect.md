# Connect the robot to Wi-Fi and LJYD

Open **Wi-Fi and LJYD Setup** in the Desktop/Hackathon-ESP32S3 folder.

1. Close Hello Demo, Arm Control and other board windows. Keep USB connected for setup.
2. Press **Connect board by USB**.
3. Enter a **2.4 GHz Wi-Fi** network name and password. Press **Save Wi-Fi and connect**. Wait several seconds and press **Refresh status**. Success means Wi-Fi shows **Online** and a nonzero IP address.
4. Ask Percy for your team's **Product ID** and **Product secret** from LJYD. These are product credentials, not your account password. Enter them in this window and press **Save team identity**.
5. Press **Connect to LJYD**. Wait and refresh. Only **LJYD: Online** confirms the cloud session; Wi-Fi Online alone does not.

Wi-Fi details and team identity are saved on the board. Passwords are hidden in the window and are not written to PC logs. Board storage is ordinary development-board storage, not an encrypted password vault. Wi-Fi reconnects after restart; cloud startup currently requires the explicit Connect to LJYD button again. Changing the product after starting cloud requires restarting the board first.

If Wi-Fi stays offline, check the network name/password, 2.4 GHz support, signal and hotspot availability. Browser-login/captive-portal and enterprise networks are not handled by this simple password setup. If Wi-Fi is online but LJYD is not, check team product credentials and the project's server environment/account binding with Percy. The setup uses the existing SDK's production environment. Do not substitute sample project credentials from source files.

The board connects through your router/hotspot directly to LJYD; the laptop is only configuring and checking it over USB. This does not yet make the laptop's arm window wireless. USB may also still be powering the board: removing it requires a suitable board supply.

The working Hello demo and manual arm controller remain available. Close this setup window before opening either. A connected cloud session and voice-agent integration are separate milestones. This update does not start microphone recording, upload camera images, enable automatic speech, or map cloud requests to motor movement. The next integration step is to agree with Percy on LJYD actions and implement a bounded local action handler, while keeping motion limits/watchdogs on the board.

Files:

- `cloud_setup.py`: simple local configuration/status window.
- `installation.json`: application hash, backup location, and actual installation checks.
- `How-to-connect.md`: these instructions.

Original source/SDK stays at C:\LJWB03. The desktop shortcut opens this canonical app; there is no second SDK installation.

## PC hotspot configured — 27 October 2026

The laptop is connected to school Wi-Fi **YOUR_UPSTREAM_WIFI**, and its **2.4 GHz mobile hotspot is YOUR_HOTSPOT**. The board successfully joined it and received **192.168.137.23** at verification. Windows showed one hotspot client and InternetAccess for the school connection. The board's IP can change later. This proves the local hotspot connection, not successful LJYD authentication.

Keep the laptop awake, connected to school Wi-Fi, and its mobile hotspot switched on. If Windows turns off the hotspot after sleep/restart, turn it back on in **Settings → Network & internet → Mobile hotspot**. The hotspot password stays in Windows and on the board; it has not been copied into these notes. The setup window now updates status automatically after USB connection and shows USB, board Wi-Fi and LJYD separately. No firmware change was needed for this switch.
