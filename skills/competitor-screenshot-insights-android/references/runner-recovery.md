# Physical Android Device Recovery

Use this runbook only after an Agent Device session, connection, or health check fails on Android. Recovery commands change device, adb, or daemon state, so diagnose first and keep the recovery bounded.

Android has no XCTest runner: nothing is built, signed, installed, or trusted on the phone, and there is no `prepare` step. Never treat "rebuild the Runner" as an Android recovery action — the equivalent question is always whether adb has a healthy, authorized transport to the device.

## Diagnose before restarting

1. Source `scripts/agent-device-env.sh`.
2. Read `agent-device session --json`, the exact `agent-device` process list, and `adb devices -l`. Consult `~/.agent-device/sessions/$AGENT_DEVICE_SESSION/daemon.log` for daemon lifecycle failures.
3. Separate these failure classes:
   - **Device missing from `adb devices -l`:** cable, port, or USB debugging is off. Restore the physical connection or ask the user to enable USB debugging. Do not reset the adb server first.
   - **Device reported `unauthorized`:** the on-device USB debugging prompt has not been accepted. Stop immediately and ask the user to accept it on the device screen, optionally choosing "always allow from this computer". Do not restart the adb server, replug, or reboot for this error — it is a permission state, not a transport fault. This is the Android analogue of the iOS certificate-trust pause.
   - **Device reported `offline`:** the transport is wedged or the device is mid-boot. This is the one class where an adb transport reset (Level 1) is the correct first action.
   - **Device locked or screen off:** capture returns black or unreadable frames while adb still reports `device`. Ask the user to unlock. Do not reset transport.
   - **adb server/client mismatch:** the log or command output mentions an out-of-date server or a different adb starting a new server. Two adb binaries are competing. Pin `CSI_ADB_BIN` to one platform-tools install rather than repeatedly restarting servers.
   - **Daemon ownership conflict:** a session may be empty while an orphan `agent-device` daemon still holds device state. Resolve and terminate only the exact matching daemon PID.
   - **Session lost (`SESSION_NOT_FOUND`):** the daemon restarted or idle-reaped the session. Recreate the session; this is not a device fault.
   - **Wrong app or package mismatch:** the target gate stopped because the foreground package or visible brand disagreed with the request. This is a target-identity stop, not a recovery case. Do not "recover" it by selecting a package manually.

Never infer that repeating the same command will fix a repeated failure with the same signature. Record the current signature and use the matching bounded recovery below.

## Evidence-driven escalation gate

Treat recovery as a state machine, not a retry counter.

1. Record a compact failure signature before each recovery action:
   - failed command;
   - error text and one distinguishing log line;
   - `adb devices -l` state for the configured device, including the `usb:` token;
   - active session and daemon state.
2. State one causal hypothesis, one condition the next action will change, and the expected evidence if that hypothesis is correct.
3. Permit another attempt only after a causally relevant condition changes. Valid changes include unlocking the device, accepting the USB debugging prompt, reseating the cable, resetting the adb transport once, removing an exact ownership conflict, or pinning a single adb binary. A new PID, a fresh timestamp, waiting longer, or rerunning the same command is not a relevant change by itself.
4. After the action, compare the new signature and state with the recorded baseline:
   - **Progress:** the relevant state changed and the expected signal appeared, such as the device moving from `offline` or `unauthorized` to `device`, a successful enumeration, or a verified target-app screenshot. Continue from that new state.
   - **No progress:** the same distinguishing signature returned and the relevant state did not change. Do not repeat the action; escalate immediately.

Use this escalation rule:

| Current result | Required next step |
| --- | --- |
| Ordinary reconnect or health action returns the same signature | Enter Level 1; do not try another ordinary reconnect. |
| Level 1 returns the same `offline`/transport signature | Level 1 has failed; request permission for Level 2. |
| Level 2 returns the same signature | Stop device operation and investigate cable, port, USB debugging, and platform-tools compatibility; do not repeat Level 2. |
| Failure class changes | Reclassify from the new evidence; do not assume either success or regression. |
| Device is `unauthorized` at any level | Leave the runbook and wait for the user's on-device authorization. |

Do not use elapsed time as the escalation criterion. A quick identical failure escalates immediately; a slow attempt does not justify repeating it. Time limits remain safeguards against a command that never returns.

## Level 1: reset the adb transport and session

Use only when the device is `offline`, a session cannot recover, or a daemon ownership conflict is confirmed. Do not use it for an `unauthorized` device or a locked screen.

1. End an active Agent Device session with `close --shutdown` when possible. If no session exists but an orphan daemon remains, verify its full command identifies the Agent Device internal daemon before terminating that exact PID.
2. Reset only the affected transport, preferring the narrowest action that can work:
   - `adb reconnect device` for a single wedged transport;
   - `adb kill-server` followed by `adb start-server` only when reconnect does not clear it. This drops every adb client on the host, so state that consequence before running it.
3. Run one `adb devices -l` check and confirm the configured device is present, in state `device`, with a `usb:` token.
4. If it is healthy, recreate the session. In research mode, use the normal target-app rules to open the intended app and establish `$AGENT_DEVICE_SESSION`, then confirm `appstate` and take one lightweight health screenshot before navigation. In modal fast-capture mode, rerun `sh scripts/fast-capture-mode.sh start`; its app-target-free session rebinding establishes `$AGENT_DEVICE_SESSION` against the current foreground without selecting or switching apps. A `SESSION_NOT_FOUND` screenshot immediately after a successful transport reset is not a device regression.

Do not run a second Level 1 reset. If the same transport signature returns, Level 1 has conclusively failed.

## Level 2: physical reconnect or device reboot

Use only with the user's permission to replug or reboot the phone.

1. Stop the exact Agent Device daemon from the failed attempt.
2. Ask the user to unplug and reseat the cable, ideally in a different port and without an intermediate hub. A failing cable or hub is the most common cause that survives Level 1.
3. If reseating does not clear it, request one full device reboot.
4. Wait for the device to return to `adb devices -l`, then ask the user to unlock it and accept any USB debugging prompt.
5. Run one enumeration probe. On success, recreate the session and take one lightweight health screenshot.

Do not repeat Level 2. If the identical failure remains, stop device operation and check cable, port, USB debugging state, and platform-tools compatibility. When a second adb binary or an out-of-date server is confirmed, pin `CSI_ADB_BIN` to one install and perform one new probe; this is a distinct configuration fix, not another Level 2 retry. Otherwise label the cause as an inference and do not create more daemons or reset loops.

## Timing and communication

- Process/device/log classification should normally take under 15 seconds.
- Each enumeration probe is capped well under the ordinary command timeout and is reported as one attempt.
- A reboot waits on device availability, not an arbitrary long sleep, and requires a fresh unlock confirmation.
- Tell the user the classified failure, the condition being changed, and the observed result. Ask for unlock or on-device authorization only when that evidence is present. A repeated unchanged signature is an escalation or stopping condition, not an invitation to retry.
