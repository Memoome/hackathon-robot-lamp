# Working together

Anyone with a GitHub account can propose code through this public repository:

1. Open https://github.com/Memoome/hackathon-robot-lamp/fork and create your fork.
2. In your fork, create a branch for your change. You can edit files in the browser or use **Add file → Upload files**. Commit the changes to that branch.
3. Click **Contribute → Open pull request**, targeting `Memoome/hackathon-robot-lamp`, branch `main`.
4. Explain your change and testing. A maintainer reviews and merges the pull request.

You can also clone your fork, edit locally and push your branch. Forks let you contribute without being granted access to the original repository.

Direct pushes to the original repository require an invitation for your specific GitHub account. Send your GitHub username to the repository owner if your team needs this. A shared link alone cannot grant write access, and anonymous direct uploads are not supported.

Create a branch or fork and open a pull request. Explain what changed and whether it was tested in preview, with simulated hardware or on the actual lamp.

For motion changes, preserve500..2500µs position command bounds, the separate continuous-base behavior, Stop, output-release warnings and connection watchdogs. No auto engagement or motion resume on USB reconnect. Include software tests when changing timing, calibration or protocol behavior.

The public cardboard profile is a reference. Save assembly-specific profiles under a new name. Review changed calibration JSON before pushing; don't replace another person's profile accidentally. Firmware/software protocol changes must account for the SDK CLI's eight-token limit.

Keep Wi-Fi/product/device secrets local. Never commit `.env`, recordings, raw flash/NVS backups, logs with payloads, toolchain installations or build output. Public docs should describe repeatable steps rather than private machine paths.

Firmware needs the organizer-provided SDK. Read firmware/README.md before applying overlays or flashing. A passing software test does not establish collision-free movement or cloud integration.
