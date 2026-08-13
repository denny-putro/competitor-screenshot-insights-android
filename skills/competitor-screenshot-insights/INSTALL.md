# Install and Preflight

Agents must read this file completely when `scripts/preflight.sh` exits `10` with `status: setup_required`. Do not load it after a normal cached run returns `status: ready`.

Do not reinstall working dependencies on every run. Inspect first, install only missing or incompatible components, and keep device names, signing identities, Team IDs, Bundle IDs, and absolute paths outside the Skill directory.

## Preflight contract

Run this local-only check before every workflow:

```sh
scripts/preflight.sh
```

- Exit `0`, `status: ready`: return to `SKILL.md`; no installation work is needed.
- Exit `10`, `status: setup_required`: complete the relevant setup below, then run `scripts/preflight.sh --record`.
- Exit `2` or malformed output: stop and report a preflight implementation error.

The cached marker lives in the user's local state directory and is invalidated only when the configuration, pinned dependencies, setup instructions, preflight implementation, or executable identities change. Override it with `CSI_INSTALL_STATE` only in a managed environment.

Preflight never contacts the phone. Device availability, unlock state, foreground App identity, and Runner health are validated later, after the required user approval.

## Supported setup

- macOS with a physical iPhone and a compatible Xcode/iPhoneOS SDK.
- A trusted, unlocked iPhone with Developer Mode enabled.
- An Apple ID and Xcode Development Team capable of signing an XCTest Runner. A paid Apple Developer Program membership is not inherently required; usable device signing is.
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
xcodebuild -version
xcrun --sdk iphoneos --show-sdk-version
command -v agent-device
agent-device --version
```

Ask before running any Agent Device command that contacts the phone, including `doctor`, or before changing Runner state, signing, Xcode selection, device state, global packages, or system-wide settings.

## Install Node.js and Agent Device

Install Node.js 22.12 or newer with the user's preferred version manager or package manager. Do not replace a compatible installation.

Install Agent Device only when unavailable or outside the supported range:

```sh
npm install -g agent-device@0.20
agent-device --version
```

Run `agent-device doctor` only after the user approves a live setup check. Classify failures before reinstalling anything.

## Prepare Xcode and the iPhone

Verify with the user that:

- the selected Xcode supports the phone's iOS version;
- the phone is paired, trusted, unlocked, and visible to Xcode;
- Developer Mode is enabled;
- Xcode has a Development Team that can sign for this phone.

Do not change the global Xcode selection merely because several versions are installed. The private Skill configuration can select one Xcode through `DEVELOPER_DIR`.

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

The location above is only a suggested per-user path. Use another stable path when appropriate. `PyYAML` is needed by validation and tests, not the normal screenshot pipeline; `scripts/run-tests.sh` bootstraps the pinned evaluation dependencies when necessary.

## Write the private machine configuration

Do not edit or replace the public `scripts/agent-device-env.sh` loader. Use `scripts/setup.sh`, which writes a mode-`600` private configuration under `$XDG_CONFIG_HOME/competitor-screenshot-insights/` or `~/.config/competitor-screenshot-insights/`.

Provide values verified on this machine:

```sh
scripts/setup.sh \
  --device "Exact iPhone name" \
  --team-id "YOUR_TEAM_ID" \
  --bundle-id "com.yourname.agentdevice.runner" \
  --xcode "/Applications/Xcode.app" \
  --stitcher-home "$HOME/.local/share/screenshot-stitcher"
```

The script discovers compatible `node` and `agent-device` executables from `PATH` unless explicit `--node-bin` or `--agent-device-bin` directories are supplied. `--session` changes the dedicated session name.

Coordinate fallback is intentionally disabled unless the device viewport is known. If it is verified, add both `--viewport-width <points>` and `--viewport-height <points>`. Never copy dimensions from another device merely to enable the fallback.

For managed environments, `--config <absolute-file>` or `CSI_AGENT_DEVICE_ENV` can select another private configuration path. Never commit that file.

App mappings learned during research are also stored in the user's private config directory. The bundled registry is only a seed, so installing or updating the Skill does not publish personal mappings or invalidate the installation cache.

## Validate and cache the local installation

Run:

```sh
scripts/preflight.sh --record
scripts/preflight.sh
```

The first command performs deeper local version/import checks, runs deterministic tests, and records success only when everything passes. The second should return `status: ready` with `cached: true`. Neither command contacts the phone.

## Prepare and trust the Runner

Runner preparation builds, signs, installs, and starts XCTest components on the phone. Obtain explicit user approval immediately before running it.

After approval, load the private configuration through the public loader and prepare once:

```sh
. scripts/agent-device-env.sh
"$AGENT_DEVICE_RAW_BIN" prepare ios-runner --platform ios --timeout 90000
```

If iOS reports that the developer certificate is not trusted, stop and ask the user to trust the named profile in **Settings > General > VPN & Device Management**. Do not repeatedly rebuild, reinstall, reboot, or change signing values for the same error.

For any other Runner startup, connection, or health failure, stop this flow and read `references/runner-recovery.md` completely before recovery.

## Completion report

Report:

1. what was already available and reused;
2. what was installed or configured, including versions but excluding private values;
3. what still requires physical user action, such as unlock, Developer Mode, Mac trust, or certificate trust.

Never print or publish Team IDs, account details, certificates, device identifiers, or machine-specific absolute paths in a reusable installation report. After setup succeeds, return to `SKILL.md`, obtain research-scope approval, and only then operate the target App.
