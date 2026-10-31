## Expanded action preview

Every action/routine preview automatically opens a separate **Lamp Studio · action preview** window. It keeps a larger side-view lamp, top-down base direction, angle relative to FRONT, a colour hue tile, actual RGB output tile, brightness bar, phase name, sound cue and progress visible together. The lamp emitter/beam changes colour too. The full-brightness hue tile helps identify very dim colours; the output tile and brightness value retain the actual commanded RGB intensity. Brightness is the peak RGB channel percentage, not a measured light level.

The view uses the existing preview frames and sends no robot commands. Stop preview cancels animation/audio, and closing this window also cancels its preview. Run previewed plan on robot uses the existing explicit playback command and snapshot checks. The final frame stays visible after playback. All five stock actions and custom routines use the view; saved calibration and physical routines are unchanged. No firmware update is needed.

## Paired routine lighting and closing stretch sound

Stretch gradually changes pale green into a more saturated, deeper green across its movement. Its original opening robot/musical cue remains; an additional original 1.65-second cute robotic ahhh plays during the closing movement, in both sound styles. This requires firmware sound slot 9 (ten sounds total).

Water introduces soft light blue, then uses a slow blue-to-white breathing pulse during its pointing invitation: two smooth pulses over a 3.2-second hold, with no hard on/off flashes. The arm and base keep their commanded pointing pose during this hold. Slump keeps its silent descent and single direct recovery: dim orange while curled, then gradually brighter orange as it rises, with the existing rising sound.

All transitions share the same smooth colour sampler in previews and real playback. Physical fades start from the ring's actual reported RGB. STOP cancels subsequent colour and audio changes, leaving the last applied colour. Sad retains its separate blue fade and Happy retains its warm pulsing light. Arm calibration and locked profiles are unchanged. Firmware preserves Wi-Fi, GPIO assignments and previous sounds. Physical motion, lights and acoustic quality still require user verification.

## Happy — cheeky chuckle

**Actions → Play Happy preview / Run Happy + sound** adds an open, lifted pose followed by four alternating base wiggles (about ±12°) and cheeky head bobs. A little nod finishes at the calibrated rest and front direction. It uses an original 1.45-second synthesized three-syllable robot chuckle through the attached speaker (new sound slot 8). Musical tones uses the existing happy musical cue instead.

The ring transitions from its actual reported colour into warm red-tinted white (RGB ratio 255:196:180), then alternates bright/dim several times with the giggles. Bright peaks are limited to a channel level of 64–180 based on the initial light level; dim beats are 22% of peak. It finishes at a softer warm light. Preview animates both arm and base and shows the lighting swatch, playing the same sound locally. Preview does not move the robot or change its physical lights.

Happy requires the updated nine-sound firmware; the previous eight-sound firmware is rejected before any action starts. The firmware retains Wi-Fi, LED control, existing sounds and GPIO assignments, and starts with servo outputs released. Engage all three bending joints and the base before playing. STOP cancels remaining movement, audio and colour updates. No physical motion or acoustic test was performed during installation.

## Sad emotion

**Actions → Play Sad preview / Run Sad + sound** is separate from the silent-descent Slump routine. Happy has not been added. Sad turns toward whichever base endpoint (500 or 2500µs) is farther from its current commanded position, lowers the face and curls inward, then holds the sad pose. It plays the existing sad robot cue, or the sad musical cue selected through the sound-style control. Check endpoint clearance before running; full software bounds are not a collision guarantee.

The real routine reads the ring's actual RGB before starting, fades that colour into blue during the turn, then dims blue to 20% of the starting peak channel by the end. If the ring is off, it fades in a low blue (about 10%) before dimming it. It stays dim blue after the routine; Stop leaves the last applied colour. The preview shows the fade in the Actions light swatch and LED colour preview, using the last known applied colour or the LED panel selection when no applied colour has been observed. Real playback always reads the board first. Preview does not send LED, sound or movement commands to the board.

Engage the position base and three arm joints before running. Existing firmware supports the action; no flash is required. Physical response has not been tested. Existing calibration, locked profiles and previous three actions are preserved.

## Current coordinated actions

Stretch sways the position base about 15° left/right while curling and opening, adds five brief small head/elbow trembles at full extension, then returns to front/rest. Water rotates about 90° away from FRONT by default while pulling back; the invitation/pointing begins only after the base command reaches its target. It returns to front with the arm. Change **Water bottle direction (0–180°)** in Rotating base and save an editable profile. Slump descends silently, holds its low pose briefly, then returns directly to good posture in a single recovery phase while the rising sound plays. Both Robot chirps and Musical tones follow this timing.

Base and arm animate concurrently in the preview, sharing duration/rate limits with playback. Engage the base once as well as the three bending joints before running Water or Stretch. The firmware reports commanded pulse position, not measured mechanical arrival; allow for actual load/servo response. These are fixed bottle coordinates, not bottle recognition. Base angle limits reflect the existing 500–2500µs model. Preview and check clearance before physical playback. STOP cancels the remaining action and freezes all commanded joints. No firmware update or autonomous physical motion was performed for this update.

## Live base dragging

After explicitly engaging the SG90 base once, drag the top-down pointer or its pulse slider to rotate the real base immediately. Drag speed controls target speed, capped at 600µs/s; release, pointer exit, focus loss or STOP freezes the current command. The pointer returns to the acknowledged command after stopping so it does not leave an unexecuted target waiting. No Move button or live-enable checkbox is needed for dragging. Before engagement it is a screen preview only. Typed pulse values and scripted previews do not automatically move the base. Use Move to preview for typed targets. Routine previews remain screen-only; routine playback uses the existing saved position checkpoints. No firmware update is required.

## Remembered power setup and automatic live dragging

External power/common ground is treated as already confirmed, as requested. Repeated servo and LED power checkboxes and the live-drag enable checkbox have been removed. Connect and explicitly engage a starting pose; after all three bending joints are engaged, a new deliberate drag of the top drawing or arm pulse slider automatically enables live movement. No extra checkbox is required after reconnecting. Connection/reconnection alone never engages a servo or resumes movement. Picture matching, range editing and routine preview remain screen-only. STOP ends the current drag; a subsequent new drag works automatically. Existing pulse bounds, speed limits and disconnect watchdogs remain in place.

## SG90 position base — current controls

The base is now a position-controlled SG90 on GPIO15, with a separate top-down view in **Rotating base**. Studio opens on this tab. Teal is the preview target; dashed gold is the last acknowledged board command. Neither is measured physical position. The drawing assumes 180° across 500–2500µs; check actual travel before using endpoints.

Support the lamp, check regulated external 5V/common ground in Servo test or Pose control, start at 1500µs, and **Engage at preview…**. First engagement can jump. Drag the top-view pointer or pulse slider to choose a target; **Move to preview** moves gradually using the existing firmware's GPIO15 jog control, capped at 600µs/s. Dragging by itself changes only the preview. STOP freezes the current command rather than sending the old continuous-servo neutral. Release outputs removes holding torque.

Use **Reverse drawing direction** if the estimated rotation is backwards. Point the real lamp forward, match the preview to its commanded pulse, then **Mark preview as FRONT**. Save an editable profile to retain the base's front, direction and preview alongside the existing arm calibration. Locked profiles are unchanged.

**Add base pose to routine** creates a position checkpoint. Reorder it among arm checkpoints in Routine; base and bending movements execute sequentially. Preview routine animates the base pointer without USB movement. Run previewed plan checks the base's starting command and front/direction calibration. Old continuous-base timed turns are retained in old files but blocked from preview/execution; replace those rows with position checkpoints. Existing three arm actions do not invent base turns.

Firmware already supports holding/jogging GPIO15 as a position channel, so no flash is required. No physical servo movement was performed to validate this update. Use your external supply; position software cannot detect mechanical collisions or force a servo beyond its real travel.

## Faster emotional routines (latest, 31 October)

The large key poses remain, but repeated sweeps and long pauses have been removed. Slump now takes about7.7seconds, Water13.1seconds and Stretch12.8seconds from the saved Rest. This is roughly33–57% shorter than the large slow versions. Quintic easing,600µs/s peak speed cap, electrical margins and watchdogs remain unchanged; no firmware change or faster raw servo command is required. Actual load/current/temperature are not measured, so software timing does not establish loaded mechanical safety. Preview and test each routine on the assembled lamp.

## Large emotional routines (earlier, 31 October)

Slump, Water and Stretch now search the full calibrated movement sector instead of restricting generated offsets to420–450µs. Generated targets stay100µs inside the500/2500 electrical edges (600–2400µs), with stick-model clearance checks along each eased segment. Joint lags are removed or a rest waypoint inserted if needed to keep a generated path above the modelled base plane. This is not a physical housing/cable/load collision model.

Slump hangs its head, folds deeply inward, makes a failed recovery attempt, then opens with relief. Water pulls back to get attention, reaches nearly fully out and points emphatically before looking back. Stretch gathers into a deep coil, unfolds almost upright, opens its face and relaxes in stages. Both existing sound styles remain supported. Custom named target checkpoints retain priority.

Shared quintic ease-in/ease-out sampling drives both the continuous screen preview and board glide commands;600µs/s cap and firmware small-step interpolation remain. Large moves take longer: approximately15s Slump,31s Water and19s Stretch from the saved Rest, depending on the active model. No sudden endpoint jumps or speed-limit bypass. Press Play preview first, then Run previewed plan. Physical movement was not tested in this change.

The locked final draft, current calibration, other profiles, GPIO assignments and LED controls are unchanged. Reopen Studio to load the new choreography. The storyboard dramatic-routines-preview.png shows representative keyframes, not the complete animated paths.

## Actual lamp motors (31 October)

Lift GPIO12 is now MG996R, elbow GPIO10 is MG90S, head GPIO11 is SG90; the MG90S base GPIO15 remains continuous rotation. Open **Servo wiring** in Studio or read [CURRENT-SERVO-WIRING.md](CURRENT-SERVO-WIRING.md) for power and calibration notes. Existing 50Hz firmware works without flashing. Full500–2500µs access is retained, but the new servo's physical endpoints and horn alignment must be checked; the old prototype calibration is not a measurement of this new lamp. Reopen Studio for updated labels.

## Larger, distinct emotional gestures (latest)

The three actions now last roughly4.5–5seconds from the selected left-facing Rest, superseding the earlier2second version. Slump curls inward/down with a heavy head, a hesitant recovery and a grateful nod; Water reaches outward with two clear pointing nods and a friendly wait; Stretch unfolds upward, raises its face and relaxes in stages. Existing robot/musical cues play with the movement.

Generated motions now search up to420µs away from Rest in the two body joints, with head adjustments up to450µs. Actual optimized changes for the saved lamp reach roughly195–330µs in the elbow/body and234–324µs in the head, depending on action. The gestures intentionally use different combinations of joints instead of forcing every servo through its full electrical travel. All pulses remain500..2500 and the existing600µs/s action cap and easing are retained. The model keeps the head on the left and above the base plane throughout sampled trajectories; it does not model full housing/link collision, force or gravity.

Open the latest Studio via the desktop launcher, then Play each preview before running. A visually inspected native storyboard is also open for comparing key poses. Older already-open Studio windows retain the previous code until reopened. The calibration and named profile were not edited during this redesign.

## Visually reviewed left-side, fast actions (31October)

Actual Studio inspection found that Starter Rest1000/600/1500 folded the head onto the right and could add a54second transition from the left-facing pose. The active action home is now **Reviewed Left Rest1000/1682/1101**, taken from the visible left-facing model. The original starter pose remains available and calibration was not changed. Both the active settings and Lamp Cardboard Prototype snapshot include the new role selection; previous snapshot is backed up.

All three stock actions now use compact six-phase easing, with a600µs/s action cap, approximately2.2s Slump,2.0s Water and2.1s Stretch when starting at Reviewed Left Rest. This dedicated action cap replaces the old60µs/s cap for these stock plans only. Custom routines/live settings remain separate. A distant initial pose still takes longer; speaker clips can finish after the motion (~2.3s). No speed limit is bypassed. User-created distant targets may also require more time.

**Use current picture as action Rest** lets you save another home explicitly. The one-click previews and Run previewed plan share the same rows and cap. Actual Studio-rendered key poses for all3 were visually inspected side by side: head/front remain left, slump tilts down, water makes a left-side invitation, stretch lifts/levels the head, all return to the same left home. Calibration points remain unchanged; this corrects the action anchor and timing, not measured physical calibration. No board commands were sent. Offline review window is open for trying previews; the older original window may still show the prior version. Reopen the regular launcher to load current code.

## Expressive routines (latest)

Studio opens at **Three actions**. Press **Play Slump preview**, **Play Water preview** or **Play Stretch preview** once to watch the complete animation with laptop audio, phase captions and playback progress. Use **Run previewed plan** afterward for the same sampled curves on the robot, or the action's Run button. Connect and engage first if you want the preview to start at the real commanded pose. The observed model stays as your observation rather than copying the animation.

- **Slump:** face droops first, links follow into a lower pose, a tiny effort to recover gives way to a soft settle, then the face notices you and leads the recovery. A small thank-you nod finishes at Rest.
- **Water:** glance toward the fixed bottle spot, lean, make one small pointing nod with the invitation cue, hold without insisting, look back toward the user, then relax to Rest. This is not bottle detection.
- **Stretch:** gather a breath with a small dip, raise the face, slowly open/lift the links, enjoy the crest, then relax in stages and finish with a contented nod.

The engine uses quintic ease-in/ease-out curves and overlapping joint delays. A high-level gesture is several soft phases, rather than one endpoint jump followed by a reverse. Sounds can overlap movement. The same curve sampler supplies both screen frames and bounded glide targets to the existing firmware, preserving its smooth on-board stepping, watchdogs and Stop. Speeds respect the routine cap; with the current60µs/s setting, the designed previews are roughly18–22seconds. A higher cap can shorten them without changing their poses, subject to their intentional breathing/holds. Actual serial/audio buffering and motor load can add delay.

Your selected Rest remains home. For action targets named Starter, the engine derives small local gestures using the calibrated head position, face direction and link geometry, searching within150µs of home for body links and limiting generated head changes to210µs. It does not silently jump to a distant inverse-kinematics solution. If you select a real checkpoint with a name other than Starter, that checkpoint takes priority as the action's main target. No physical collision or load model is included; check the complete preview and clearance before running. Base yaw is deliberately absent because there is no repeatable heading feedback.

The calibration/profile/checkpoints are unchanged. `expressive-plan-reference.json` records the plans generated from the currently saved geometry for agent review; Studio regenerates from the active profile. Software checks verify model slump lowering/stretch rising, exact return, no-overshoot/rate caps, fullbounds, both styles, one-click complete screen playback without USB commands, and hardware sampler sequencing. No actual robot motion or physical sound timing was tested in this update. Reopen Studio to load it.

## Automatic USB connection

**Auto reconnect USB** is enabled when Studio opens. The app finds the board by its known USB identity even if its COM number changes. After cable removal it cancels live dragging/unfinished plans, clears stale board position, and retries when that board reappears. Failures back off up to10seconds between attempts. No servo engagement, resumed routine, automatic firmware upload or live-control enable occurs on reconnect. Check external power/common ground and engage the supported lamp again before movement.

Use **Disconnect…** to release the supported lamp, close the port and pause automatic connection while loading a profile or working offline. Re-enable Auto reconnect USB or click Connect board afterward. A second controller can still hold the port; close/release it first. A visible port with unresponsive/incompatible firmware is reported as a timeout rather than falsely marked connected.

## Lamp anatomy in both views

The stick figure now includes a pedestal base, lower arm, upper arm and a shaded lamp head with a bright light-emitting face. A beam and FRONT arrow show the assumed direction it faces. J1 Lift is the mount pivot (GPIO12), J2 Elbow is the middle pivot (GPIO10), and J3 Head tilt is the final hinge (GPIO11). The final segment represents head orientation. Joint rings indicate axes of rotation; the colored downstream endpoints remain the drag handles for their preceding joints, as before. Base rotation is still GPIO15 with unknown heading.

**Flip lamp face**, beside the visible arc buttons, reverses the head's displayed front in both models without changing pulse calibration, saved checkpoints or servo commands. Save profile afterward to include this preference in Lamp Cardboard Prototype. If you change the face direction after previewing, preview again before running that plan.

The anatomy is a visual interpretation to verify against the real lamp, not automatic knowledge of its geometry. No movement routines were guessed or rewritten for this drawing update. Use the lamp-shaped preview to check whether Rest, Slump, Bottle and Stretch actually point the head as intended. Reopen Studio to see the details.

## Saved prototype and preview-before-running

The current saved preferences are preserved as **Lamp Cardboard Prototype** in `profiles/Lamp Cardboard Prototype.json`. Calibration points, direction fixes, full-range settings, lengths, checkpoints, roles and custom routine are included. Use **Save profile** to update this named snapshot after further changes; type another name before saving to keep separate versions. **Load profile** restores the selection while offline. Loading never connects, engages or enables live control. Current loaded settings remain editable, including ranges and calibration. Saving the named profile also captures current UI settings and preview/observed figure preferences. Older snapshot overwrites retain a `.previous.json` copy.

For Slump, Water or Stretch, choose **Preview** in Three actions. For a custom sequence choose **Preview routine on screen** in Routine. The top figure animates the same per-joint pulse-rate logic as firmware: joints travel at a common speed and shorter moves stop earlier, respecting the selected cap. The laptop plays each sound on arrival, followed by the saved pause. Screen preview automatically disables live dragging and sends no robot commands. Base turns are shown as timed commands with unknown heading, not invented angles.

After watching the whole preview, choose **Run previewed plan** in the top bar. This uses the frozen checkpoint pulses, speed cap, timing and sounds from that preview, even if you subsequently change the routine controls. It refuses to run if calibration changed or the board's starting pulse pose differs. Connect and engage the real lamp first, then preview from that current commanded pose for the closest comparison. With offline previews you may need to preview again after connection/engagement. Direct Run buttons still work too.

STOP cancels screen animation and laptop sound, as well as the robot's pending routine when connected. Editing the control arm cancels a screen preview. The observed figure is never animated by a routine. Sound timing uses asset lengths; physical speaker buffering and motor load may add delay. Preview models commanded geometry; it does not detect collisions, stalls or sagging.

Checks passed for full pulse bounds, range orientation and profile persistence, preview/common-rate math, screen-only playback, cancellation, snapshot consistency and existing live/base/three-action behavior. No hardware motions were performed during this update. Reopen Lamp Studio after supporting/releasing an active controller to load these changes.

**Full pulse range enabled:** All three position joints now use500–2500µs through sliders and visual dragging. Startup and saving prevent calibration samples from narrowing this interval. Corrections align the full-range geometry. Reopen Studio to load it. No firmware change or physical movement was performed.

## Range controls are now above the control arm

Reopen Lamp Studio and look for **Movement arc · always available here**, directly above the top drawing. No tab search is necessary.

- Choose Lift, Middle or Head in the visible dropdown.
- **Use full180°** immediately restores that selected joint's visual mapping over its configured pulse bounds, preserving its current estimated angle and corrected direction. No robot movement is sent.
- **Rotate arc…** enters picture-only editing. Drag the white RANGE handle, or use the5° buttons. **Save arc** applies the new sector, **Cancel** discards it.
- The visible summary shows the selected joint's current mapped span and pulse bounds.

Inspection of the user's saved calibration showed lift847–1176µs (~33°), middle600–2365µs (~125°), and head1057–1500µs (~21°). Inverse dragging clamps to those observations. This explains the differing visual movement ranges; it is not evidence that the real lift/head have narrower physical travel. No horn repositioning is required to fix this software mapping issue. If real motion still binds at a mechanical stop, narrow the physical command limits rather than forcing it. The earlier Hello trial does not establish clearance of every pose on the new assembly.

## Adjustable joint range (latest)

The earlier visual mapping could stop at the calibration samples: for example the lift samples847–1176µs prevented dragging past1176 even though configured pulse bounds were500–2500. The Joint range tab fixes this without changing hardware firmware.

1. Reopen Lamp Studio. Click a colored control-arm endpoint to select that joint, or select Lift/Middle/Head in **Joint range**. The arc around its rotation pivot shows the current estimated range, with pulse values at its ends.
2. Enable **Edit180° range**. Live control is switched off and movement commands are locked while editing.
3. Drag the white **RANGE** handle around the pivot to orient the180° sector. You can also use the rotation slider or5° buttons.
4. Press **Save full180° range for selected joint**. The app maps its configured pulse bounds (normally500–2500µs) over this sector while retaining that joint's corrected direction. No motor command is sent.
5. Test slowly, check clearance, and align the observed arm if necessary. Observed-arm matches now shift a saved full-range sector without shrinking its pulse interval. Existing checkpoint pulse values are retained.

This is an adjustable visual estimate of the servo's travel, not a change to its physical limits. A linkage can collide or bind before the electrical endpoints.180° is a starting model, not a guarantee for this assembly. Editing the range does not change the configured pulse limits or command extra travel beyond them. The bottom figure remains your manually observed pose.

## Two-arm live control (latest update)

Reopen Lamp Studio. Joint1 lift drawing direction is now reversed once, like the earlier head/base corrections. Recorded pulse checkpoints remain intact.

**Top: CONTROL ARM.** This is the program's estimated pose. Connect, check external power/common ground, support the lamp and Engage once. Tick **Enable live dragging** once per connection. Drag the top arm or pulse sliders to send motion immediately. Faster dragging requests higher speed; slower dragging requests lower speed. The separate Live speed limit defaults600µs/s, bounded10..600. Physical speed is limited by firmware, mechanism and load; instant following is not guaranteed. Release, leave the control area, lose window focus, STOP, a stale drag stream or loss of the app heartbeat stops motion. After stopping, the top arm adopts the last commanded position. There is no deferred catch-up movement after release. Startup is never automatically armed.

**Bottom: OBSERVED ARM.** Wait for the lamp to hold still. Drag the bottom joint endpoint to match what you see, then release. This saves a calibration observation automatically at the board's current commanded pulse for that joint. It sends no hardware movement. When offline, it pairs with the preview pulses instead; these are hypothetical until verified on hardware. First observation aligns the offset, second observation at another pulse teaches direction and travel, further observations refine the fit. Calibrate lift first, then middle, then head. The bottom figure is your observation, not a sensor feed; it stays as you left it until you adjust it again.

All three action buttons, base controls and custom checkpoint routines remain in Studio. They use the updated mapping for visual editing. Existing stored pulse routines keep their recorded values. The previous button-based preview controls below remain useful when live dragging is disabled. The base still has no heading feedback.

# Lamp Studio

Open **Desktop → Hackathon-ESP32S3 → Lamp Studio**. Close the earlier Lamp Demo controller after supporting the lamp and releasing its outputs before connecting this one. The board already has the required lamp firmware. Launching this program does not connect, move or play sound automatically.

## Start with the drawing

The three colored links are lift GPIO12, middle GPIO10 and head GPIO11. Drag a colored endpoint or adjust its pulse slider. These edits change the preview only. The dashed figure is the last board-command estimate; it is not measured feedback. The initial angles and link lengths are placeholders. The base does not rotate in this editor.

For a real movement: Connect board, check external servo power/common ground, support the lamp, and choose **Engage at preview pose**. Initial engagement can jump because the board cannot measure the current shaft positions. Subsequent **Move gradually to preview pose** commands use the existing smooth ramp, with a default speed cap of60µs/second. STOP cancels the remaining sequence and holds current targets while connected. Release and closing can let the lamp fall.

## Easy calibration

Reopen Lamp Studio to load the updated controls. In Calibrate drawing:

1. Choose Lift, Middle or Head. If it goes the opposite way in the picture, press **Reverse direction for this joint**. This sends no robot movement and keeps the current picture angle anchored.
2. Position the real lamp using Pose control and let it stop. Press **Match picture to current lamp position**. When connected, this uses the board's current commanded pulses rather than an unsent preview.
3. Drag that joint's colored endpoint until the picture matches what you see. Or use **Bend picture left/right** for small changes. The robot is locked against movement while matching.
4. Press **Picture matches — save this position**.
5. Move that same real joint a little, let it stop, then repeat matching. The first match aligns the picture; the second teaches direction and travel. Repeat for Lift, Middle and Head in that order.

The base stays stationary. No angle numbers or endpoint pulses are required for this flow. Matching changes only the selected joint; its child links naturally follow. Calibration records and saved checkpoints remain in visual-lamp.json. Drawing angles are estimates of commanded positions, with no sensor feedback. Outside two observed positions the drawing clamps rather than inventing travel. You can add more matching positions to improve the mapping. If repeated positions imply conflicting directions, the app asks you to correct the observation.

The advanced numbers and link length fields are available under **Show / hide advanced numbers & link lengths**. Use them only if needed. Enter pivot-to-pivot link lengths in any consistent unit. STOP and Release remain available throughout.

## Checkpoints and routines

Save preview poses with names such as Rest, Bottle and Stretch. Load them into preview before sending them. Use **Use last commanded pose in preview** to copy the latest board pulse values, then save that as a checkpoint if useful.

Select a named checkpoint, choose movement seconds in Pose control, choose pause/sound in Routine, and press **Append selected checkpoint**. Add more rows, reorder with arrows, or remove and re-add a row to change its settings. Each row stores a snapshot of its pulse values; changing the named checkpoint later does not change rows already appended.

**Preview routine on screen** animates the planned moves without board commands. Sounds are labels only during screen previews; pauses exclude sound duration. The real run moves to each checkpoint, plays the selected sound on arrival, then pauses. Distance and speed cap can make a move take longer than the requested time. **Run routine on robot** requires an engaged lamp and explicit confirmation. STOP cancels later checkpoints and sounds.

Suggested routines after YOU calibrate the poses:

- Water: Rest → Bottle (water cue,1.2second pause) → Rest.
- Stretch: Rest → Stretch (stretch cue,2second pause) → Rest (happy cue).

Everything is saved in `visual-lamp.json` beside the app: calibration, lengths, checkpoint pulses and routine. This is also the file the agent can read to understand your calibrated robot. Existing Lamp Demo poses are kept separately. Physical tests and calibration are still required.

## Rotating base (GPIO15)

Reopen Lamp Studio and choose **Rotating base**. Check power/common ground in Pose control, connect, then hold Left or Right. Default speed is5% command strength. Releasing the button, leaving it, losing window focus or STOP ends the turn. Each press is limited to10seconds. The firmware also stops rotation if renewal commands stop. Keep cables untwisted. No base angle is measured or inferred from command duration; the side view does not rotate.

Use **Swap left / right directions** if the controls are reversed. Stop pulse defaults1500µs; adjust slightly within1400..1600 if the continuous servo creeps. Set a0.1..10second duration and **Add left/right turn to routine** to insert a timed base checkpoint. During that row the other joints hold their previous commands. Position and base turns are sequential in this version. Screen preview labels the timed turn; it cannot show a reliable heading without position feedback. Existing calibration/checkpoints are preserved.

## Direction correction and all three actions

Reopen Lamp Studio to load the corrected base left/right direction and head joint3 (GPIO11) visual mapping. The direction correction is saved once; reopening does not keep toggling it. Saved raw checkpoint pulses and custom routine rows retain their recorded values. Newly loaded starter checkpoints use reversed head movement; starters remain estimates to calibrate.

The **Three actions** tab runs Slump, Water and Stretch with robot or musical sounds. Select the saved checkpoint for Rest, Slump, Water and Stretch, then Save action checkpoint choices. The current project has editable starter checkpoints preselected. Replace them with your observed positions as you calibrate. Preview is screen-only; Run plays through the attached robot speaker. All actions start at Rest, visit their action checkpoint and return to Rest. Slump/stretch hold2seconds after their cue, water holds1.2seconds. Slump/stretch finish with a happy cue on return. Sound plays on arrival, as for custom routines. Movement time and speed cap come from Pose control.

Connect and engage the initial pose in Pose control before Run. No firmware change is needed. All action controls and custom checkpoint routines now live in Lamp Studio.
# Servo orientation test (31 October 2026)

Studio now opens at **Servo test**, with independently applied pulses for Lift MG996R (GPIO12), Elbow MG90S (GPIO10), and Head SG90 (GPIO11). No output engages on launch or connection. Check the shared external-power/common-ground/support box, then use **Apply pulse…** on one joint at 1500µs. Initial engagement can jump; support/unload the lamp before fitting its horn. **− Step / + Step** change only that joint from its last acknowledged command, by 10µs by default. The input beside Apply is a proposed pulse, while the status beneath it shows the last board command; that command is not measured position. Large steps ask for confirmation. Software bounds remain 500–2500µs and steps clamp to them. The new lift should initially be checked within 1000–2000µs and extended gradually only while it moves freely. Stop at binding or buzzing rather than forcing a physical endpoint. Rotating base remains a continuous speed control on GPIO15 in its separate tab.

STOP and Release outputs now reserve space at the bottom of the window. Release removes holding torque; support the lamp first. Existing drawings, calibration, profiles, routines and adjustment tools are retained. Save a separate profile for the new servo/horn arrangement before using old routines. The existing firmware supports this test; no firmware change is required when Studio connects normally.

