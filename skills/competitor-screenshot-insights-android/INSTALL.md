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

The device must expose an authorized adb interface over a USB cable. Walk the user
through the steps below; every one of them happens on the phone, so none of it can
be done for them.

### 1. Enable Developer options

Tap the build number seven times. The path differs by vendor:

| Vendor | Path |
|---|---|
| Huawei / Honor (EMUI) | **Settings → About phone → Build number** |
| Samsung (One UI) | **Settings → About phone → Software information → Build number** |
| Xiaomi (HyperOS / MIUI) | **Settings → About phone → MIUI version** (or **OS version**) |
| Pixel / stock Android | **Settings → About phone → Build number** |
| Oppo / realme / vivo | **Settings → About device → Version → Build number** |

A toast confirms "You are now a developer". Some devices ask for the screen lock PIN.

### 2. Enable USB debugging

Open Developer options — usually **Settings → System & updates → Developer options**
(EMUI), or **Settings → System → Developer options** on stock Android — and turn on
**USB debugging**.

### 3. Make sure adb is allowed in the current USB mode

This is the step most often missed, and the failure looks like a missing device
rather than a settings problem. Many devices default the USB connection to
*charge only*, which blocks adb. Either:

- turn on **Allow ADB debugging in charge only mode** in Developer options, **or**
- after connecting, pull down the notification shade, tap the USB notification, and
  choose **Transfer files** / **MTP**.

The toggle is the more durable choice if the device will be used repeatedly.

### 4. Connect the cable

Connect the phone directly to the computer with a USB cable — avoid hubs and
docks, which are a common cause of a device that authorizes and then drops to
`offline`. Unlock the phone.

Fast capture mode is wired-only by design. An adb-over-network target
(`adb connect host:port`) carries no `usb:` transport token and is rejected at
activation, so wireless debugging cannot substitute for the cable.

### 5. Accept the authorization prompt

A dialog titled **Allow USB debugging?** appears on the phone, showing this
computer's RSA key fingerprint. Tick **Always allow from this computer**, then
accept.

If the dialog never appears:

1. turn on **Always prompt when connecting to USB** in Developer options;
2. set the USB mode to **Transfer files** (see step 3);
3. unplug and replug the cable.

Only if it still does not appear, use **Revoke USB debugging authorizations** in
Developer options and replug — that forces a fresh prompt. Do not start with this
step: it clears every computer the phone has previously trusted.

### 6. Verify

Ask for approval before the first command that reaches the phone, then:

```sh
adb devices -l
```

The configured device must appear in state `device` with a `usb:` token, for example:

```
1A2B3C4D    device usb:337641472X product:raven model:Pixel_6_Pro device:raven
```

Interpret anything else as follows:

| Reported state | Meaning | Action |
|---|---|---|
| `unauthorized` | The prompt in step 5 was not accepted | Ask the user to accept it on the phone. This is a permission state, not a transport fault — do not restart the adb server, replug, or reboot for it |
| `offline` | Transport wedged, or the device is mid-boot | Reseat the cable; see `references/runner-recovery.md` before escalating |
| not listed at all | Cable, USB mode, or USB debugging is off | Re-check steps 2–4 |
| serial looks like `host:port` | This is adb-over-network | Connect by cable; fast mode rejects it |
| device present but no `usb:` token | Same as above | Connect by cable |

Record the **adb serial**, not the marketing name, for `setup.sh --device`. Model
tokens are internal codes — a Huawei P30 reports `model:ELE_L29`, so passing
"Huawei P30" fails the wired-device gate and the error reads as "device not
visible", which points at the wrong cause.

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
