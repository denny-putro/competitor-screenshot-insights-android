# Install and Preflight (Android)

Agents must read this file completely when `sh scripts/preflight.sh` exits `10` with `status: setup_required`. Do not load it after a normal cached run returns `status: ready`.

Do not reinstall working dependencies on every run. Inspect first, install only missing or incompatible components, and keep device names, adb serials, and absolute paths outside the Skill directory.

## Preflight contract

Run this local-only check before every workflow:

```sh
sh scripts/preflight.sh
```

- Exit `0`, `status: ready`: return to `SKILL.md`; no installation work is needed.
- Exit `10`, `status: setup_required`: complete the relevant setup below, then run `sh scripts/preflight.sh --record`.
- Exit `2` or malformed output: stop and report a preflight implementation error.

The cached marker lives in the user's local state directory and is invalidated only when the configuration, pinned dependencies, setup instructions, preflight implementation, or executable identities change. Override it with `CSI_INSTALL_STATE` only in a managed environment.

Preflight never contacts the phone. It probes local executables only and does not run `adb devices`, so it never starts an adb server or wakes the device. Device availability, authorization state, unlock state, foreground app identity, and session health are validated later, after the required user approval.

## Supported setup

- macOS or Linux with a physical Android device.
- A device with **Developer options** and **USB debugging** enabled, connected by USB cable and unlocked.
- Android platform-tools providing `adb`. No Xcode, no Apple Developer account, no signing identity, and no XCTest runner are involved.
- Node.js 22.12 or newer.
- Agent Device CLI 0.20.x.
- Python 3.12 or newer with the pinned screenshot runtime.

The optional `build-competitor-report-html` Skill is needed only when the user requests the default HTML report in addition to screenshot evidence.

## Inspect before installing

Resolve the installed Skill directory, then run read-only host checks:

```sh
node --version
npm --version
python3 --version
command -v adb
adb version
command -v agent-device
agent-device --version
```

`adb version` reports the local client only and contacts no device. Ask before running any command that reaches the phone — including `adb devices`, `agent-device devices`, and `agent-device doctor` — or before changing device state, global packages, or system-wide settings.

## Install Node.js and Agent Device

Install Node.js 22.12 or newer with the user's preferred version manager or package manager. Do not replace a compatible installation. Agent Device declares `engines: node >=22.12`, so an older Node fails regardless of platform.

Install Agent Device only when unavailable or outside the supported range:

```sh
npm install -g agent-device@0.20
agent-device --version
```

Run `agent-device doctor` only after the user approves a live setup check. Classify failures before reinstalling anything.

## Install Android platform-tools

Agent Device resolves `adb` through `ANDROID_HOME`, `ANDROID_SDK_ROOT`, or `PATH`. Install platform-tools only when `adb` is unavailable:

- Android Studio's SDK Manager installs it at `~/Library/Android/sdk/platform-tools` on macOS.
- Standalone platform-tools packages, Homebrew (`brew install --cask android-platform-tools`), or a distribution package also work.

Do not install a second SDK when a working `adb` already exists.

## Prepare the Android device

Verify with the user that:

- Developer options are enabled;
- USB debugging is enabled;
- the device is connected by USB cable and unlocked;
- the USB debugging authorization prompt for this computer has been accepted.

If `adb devices` later reports the device as `unauthorized`, stop and ask the user to accept the on-device USB debugging prompt (optionally checking "always allow from this computer"). Do not repeatedly restart the adb server, replug, or reboot for the same authorization error.

Fast capture mode is wired-only by design. An adb-over-network target (`adb connect host:port`) carries no `usb:` transport token and is rejected at activation.

## Install the screenshot runtime

Create an isolated Python environment at a stable location chosen by the user. From the installed Skill directory:

```sh
python3.12 -m venv "$HOME/.local/share/screenshot-stitcher"
"$HOME/.local/share/screenshot-stitcher/bin/python" -m pip install \
  -r requirements-runtime.txt
```

Confirm the environment:

```sh
"$HOME/.local/share/screenshot-stitcher/bin/python" -c 'import cv2, numpy'
"$HOME/.local/share/screenshot-stitcher/bin/screenshot-stitcher" --help
```

The location above is only a suggested per-user path. Use another stable path when appropriate. This environment is platform-independent: stitching, scroll-segment selection, frame extraction, and the deterministic checks are identical on Android and iOS. `PyYAML` is needed by validation and tests, not the normal screenshot pipeline; `scripts/run-tests.sh` bootstraps the pinned evaluation dependencies when necessary.

## Write the private machine configuration

Do not edit or replace the public `scripts/agent-device-env.sh` loader. Use `sh scripts/setup.sh`, which writes a mode-`600` private configuration under `$XDG_CONFIG_HOME/competitor-screenshot-insights-android/` or `~/.config/competitor-screenshot-insights-android/`.

Provide values verified on this machine:

```sh
sh scripts/setup.sh \
  --device "Exact device or model name" \
  --stitcher-home "$HOME/.local/share/screenshot-stitcher"
```

Only `--device` is required; Android needs no Team ID and no runner bundle ID. The script discovers compatible `node`, `agent-device`, and `adb` executables from `PATH`, `ANDROID_HOME`, or `ANDROID_SDK_ROOT` unless explicit `--node-bin`, `--agent-device-bin`, `--android-sdk`, or `--adb` values are supplied. `--session` changes the dedicated session name.

Add `--serial <adb-serial>` when several Android devices are attached. The wired-connection gate rejects an ambiguous match and asks for exactly this value, matched against the adb serial rather than a display name.

Coordinate fallback is intentionally disabled unless the device viewport is known. If it is verified, add both `--viewport-width <points>` and `--viewport-height <points>`. Never copy dimensions from another device merely to enable the fallback.

For managed environments, `--config <absolute-file>` or `CSI_AGENT_DEVICE_ENV` can select another private configuration path. Never commit that file.

App mappings learned during research are also stored in the user's private config directory. The bundled registry is only a seed, so installing or updating the Skill does not publish personal mappings or invalidate the installation cache.

## Validate and cache the local installation

Run:

```sh
sh scripts/preflight.sh --record
sh scripts/preflight.sh
```

The first command performs deeper local version/import checks, runs deterministic tests, and records success only when everything passes. The second should return `status: ready` with `cached: true`. Neither command contacts the phone.

## Confirm the device is reachable

Android has no Runner to build, sign, install, or trust, so there is no `prepare` step and nothing is installed on the phone at setup time. The first command that reaches the device is a plain enumeration. Obtain explicit user approval immediately before running it.

After approval, load the private configuration through the public loader and confirm the device:

```sh
. scripts/agent-device-env.sh
"$AGENT_DEVICE_RAW_BIN" devices --platform android
```

Expect the configured device in state `device`. If it reports `unauthorized`, stop and ask the user to accept the on-device USB debugging prompt. If it reports `offline` or is missing, ask the user to reconnect the cable and unlock the device.

For any other session, connection, or health failure, stop this flow and read `references/runner-recovery.md` completely before recovery.

## Completion report

Report:

1. what was already available and reused;
2. what was installed or configured, including versions but excluding private values;
3. what still requires physical user action, such as unlock, enabling USB debugging, or accepting the USB debugging authorization prompt.

Never print or publish adb serials, device identifiers, account details, or machine-specific absolute paths in a reusable installation report. After setup succeeds, return to `SKILL.md`, obtain research-scope approval, and only then operate the target App.
