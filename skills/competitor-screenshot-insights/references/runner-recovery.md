# Physical iPhone Runner Recovery

Use this runbook only after an Agent Device Runner startup, connection, or health check fails. Recovery commands change device or Runner state, so diagnose first and keep the recovery bounded.

## Diagnose before restarting

1. Source `scripts/agent-device-env.sh`.
2. Read `agent-device session --json`, the exact Agent Device/XCTest process list, the device details, and the tail of `~/.agent-device/sessions/$AGENT_DEVICE_SESSION/runner.log`.
3. Separate these failure classes:
   - **Device unavailable or locked:** restore the physical connection or ask the user to unlock. Do not rebuild the Runner.
   - **Build, signing, provisioning, or install failure:** fix that exact error. Do not reset XCTest transport.
   - **Developer certificate not trusted:** the log says `Developer App Certificate is not trusted` or that the profile `has not been explicitly trusted by the user`. Stop immediately and ask the user to trust the named developer profile in **Settings → General → VPN & Device Management**. Do not rebuild, reboot, uninstall, or classify this as a DTX failure.
   - **Runner ownership conflict:** a session may be empty while an orphan `agent-device` daemon still owns the Runner. Resolve and terminate only the exact matching daemon PID.
   - **XCTest/DTX bootstrap failure:** the log contains `TEST BUILD SUCCEEDED`, then the Runner starts, followed by `Connection peer refused channel request for "dtxproxy:XCTestDriverInterface:XCTestManager_IDEInterface"`, `Exiting due to IDE disconnection`, or exit code `74` before connection. Treat cache and signing as already cleared when a fresh build succeeded.
   - **Xcode/device SDK mismatch:** compare `xcodebuild -version`, `xcrun --sdk iphoneos --show-sdk-version`, and the device OS. When Apple’s compatibility table confirms that the selected Xcode predates the device’s supported SDK family, upgrade or select a matching Xcode before another Runner recovery. Persist the working `DEVELOPER_DIR` in `scripts/agent-device-env.sh` so a later shell cannot silently fall back to the older global Xcode.

Never infer that another `prepare` will fix a repeated failure with the same signature. Record the current signature and use the matching bounded recovery below.

## Evidence-driven escalation gate

Treat recovery as a state machine, not a retry counter.

1. Record a compact failure signature before each recovery action:
   - failed command;
   - error domain/code and one distinguishing log line;
   - device connection and lock state;
   - active session, daemon, `xcodebuild`, Runner, and `testmanagerd` state.
2. State one causal hypothesis, one condition the next action will change, and the expected evidence if that hypothesis is correct.
3. Permit another attempt only after a causally relevant condition changes. Valid changes include unlocking or reconnecting the device, trusting the named certificate, removing an exact ownership conflict, replacing the stale `testmanagerd` process, or selecting a compatible Xcode. A new PID, a fresh timestamp, waiting longer, or rerunning the same command is not a relevant change by itself.
4. After the action, compare the new signature and state with the recorded baseline:
   - **Progress:** the relevant state changed and the expected signal appeared, such as `AGENT_DEVICE_RUNNER_LISTENER_READY`, a successful health probe, a verified target-app screenshot, or a materially different failure class. Continue from that new state.
   - **No progress:** the same distinguishing signature returned and the relevant state did not change. Do not repeat the action; escalate immediately.

Use this escalation rule:

| Current result | Required next step |
| --- | --- |
| Ordinary reconnect or health action returns the same Runner/DTX signature | Enter Level 1; do not try another ordinary reconnect or `prepare`. |
| Level 1 returns the same DTX/code-74 signature | Level 1 has failed; request permission for Level 2. |
| Level 2 returns the same signature | Stop device operation and investigate toolchain compatibility; do not repeat Level 2. |
| Failure class changes | Reclassify from the new evidence; do not assume either success or regression. |

Do not use elapsed time as the escalation criterion. A quick identical failure escalates immediately; a slow attempt does not justify repeating it. Time limits remain safeguards against a command that never returns.

## Level 1: clean Runner and XCTest transport

Use only when the Runner is unavailable, a session cannot recover, or the XCTest/DTX signature above is present.

1. End an active Agent Device session with `close --shutdown` when possible. If no session exists but an orphan daemon remains, verify its full command identifies the Agent Device internal daemon before terminating that exact PID.
2. Confirm no Agent Device `xcodebuild` or Runner process remains. Do not kill unrelated Xcode processes.
3. Terminate the device `testmanagerd` process once through `devicectl`; iOS will recreate it when XCTest starts.
4. Run one `prepare ios-runner --platform ios --timeout 90000` health probe.
5. If the probe succeeds, remember that `prepare` proves Runner health but may not create an App session. Use the normal target-app rules to open the intended app and establish `$AGENT_DEVICE_SESSION`, then confirm `appstate` and take one lightweight health screenshot before navigation. A `SESSION_NOT_FOUND` screenshot immediately after a successful `prepare` is not a Runner regression.

Do not run a second Level 1 probe. If the same DTX/code-74 signature returns after a fresh build, Level 1 has conclusively failed.

## Level 2: reinstall after device reboot

Use only with the user's permission to reboot the phone.

1. Stop the exact Agent Device daemon from the failed probe.
2. Uninstall only the configured Runner test bundle.
3. Request one full device reboot.
4. Wait for the physical iPhone to return, then ask the user to unlock it and approve any trust or Developer Mode prompt.
5. Run one `prepare ios-runner --platform ios --timeout 90000` probe. If iOS reports an untrusted Developer App certificate after reinstall, pause for the user's explicit trust action and then resume the same probe once; this permission pause is not another recovery cycle. On success, confirm the session and take one lightweight health screenshot.

Do not repeat Level 2. If the identical bootstrap failure remains, stop device operation and check Xcode/iOS XCTest transport compatibility. When Apple’s official compatibility matrix confirms that the selected Xcode is behind the device SDK family, upgrade or select the matching Xcode and perform one new version-change probe; this is a distinct toolchain fix, not another Level 2 retry. Otherwise label compatibility as an inference and do not create more daemons or rebuild loops.

## Timing and communication

- Process/device/log classification should normally take under 15 seconds.
- Each `prepare` probe is capped at 90 seconds and is reported as one attempt.
- A reboot waits on device availability, not an arbitrary long sleep, and requires a fresh unlock confirmation.
- Tell the user the classified failure, the condition being changed, and the observed result. Ask for unlock or trust only when that evidence is present. A repeated unchanged signature is an escalation or stopping condition, not an invitation to retry.
