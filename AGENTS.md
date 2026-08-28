# Competitor Screenshot Insights (Android) maintenance agreement

Adapted from the upstream agreement in
[`fengjunnan-web/competitor-screenshot-insights`](https://github.com/fengjunnan-web/competitor-screenshot-insights)
(MIT). The publication discipline is upstream's and is kept deliberately; the
platform, runtime, and validation specifics are rewritten for this Android fork.

This file applies to the entire repository.

## Scope and sources of truth

- **This repository** is the canonical source for the Android port. Treat
  `~/.claude/skills/competitor-screenshot-insights-android` as a runtime
  deployment or test candidate, never as an independent source of truth.
- **Upstream is read-only.** `fengjunnan-web/competitor-screenshot-insights` is
  the origin of this work, not a push target. Never push, open a pull request
  against, tag, or release anything on upstream from this repository.
- This fork **replaced** upstream's `skills/competitor-screenshot-insights` with
  `skills/competitor-screenshot-insights-android`. Merging upstream changes will
  therefore conflict in that directory by design. Port upstream changes
  selectively; do not resolve such a conflict by restoring the iOS Skill.
- The Skill's `name:` frontmatter must equal its folder name — `validate_skill.py`
  enforces it and CI runs the validator. Renaming the folder means renaming the
  Skill, and vice versa.

## Default rule

A bug report or change request authorizes local diagnosis, modification, and
testing only. It does not authorize a push, pull request, merge, tag, GitHub
release, or replacement of an existing public release.

Publish only after the user explicitly says the candidate is satisfactory and asks
to publish it. If the instruction is ambiguous, keep the work local and report what
remains to be verified.

## Iteration workflow

1. Preserve `main` and existing release tags while experimenting. Start a local
   `android/<topic>` branch from the current public baseline.
2. Reproduce or characterize the reported behavior before changing it. Record the
   actual failure evidence rather than relying only on a proposed diagnosis.
3. Make intentional edits in this repository. Never copy an installed Skill
   wholesale back into the repository; selectively port reviewed changes so private
   configuration, state, screenshots, recordings, caches, device serials, and app
   mappings learned at runtime cannot enter the public source.
4. Add or update a regression test for a defect whenever the behavior can be tested
   deterministically. Prefer pinning the **real device-observed format** — several
   defects in this fork were plausible-looking code that only a physical device
   disproved.
5. Run validation appropriate to the change. Iterate locally until the candidate is
   satisfactory.
6. When real-device validation is required, deploy with `sh deploy.sh` as a
   reversible test step. Do not treat that deployment as publication. Note the
   install fingerprint covers file paths, so any relocation or re-copy requires
   `preflight.sh --record` again; `deploy.sh` handles that.
7. Report the result and wait for user acceptance. Continue editing when the user
   is not satisfied.
8. Enter the release workflow only after explicit publication approval.

## Validation policy

- For any Skill change, run
  `sh skills/competitor-screenshot-insights-android/scripts/run-tests.sh` and
  `sh scripts/release-check.sh`.
- **`release-check.sh` can pass falsely.** Its privacy scan calls `rg`; if ripgrep
  is not a real executable on `PATH`, the scan is skipped and the script still
  prints `PASS`. Where `rg` is a shell alias or absent, run the equivalent
  manually before trusting the result:

  ```sh
  git ls-files -z | xargs -0 grep -nEI '(/Users/|com\.fengjunnan|9FQYYJMFS8|gh[opusr]_[A-Za-z0-9_]{20,})'
  ```

- For capture, navigation, target identity, scrolling, popup, advertisement,
  horizontal-container, or device-transport behavior, also validate the affected
  journey on a **physical Android device**. Confirm the original failure is gone and
  preserve evidence of the result.
- For installation, setup, preflight, path, dependency, or packaging changes,
  validate both a new-user `setup_required` path and an existing-user cached `ready`
  path. Also test the GitHub archive installation mode where executable bits are
  absent.
- Documentation-only changes do not require phone operation, but still require
  release hygiene and relevant structure/link checks.
- A passing test suite is necessary but does not replace real-device validation for
  behavior that depends on a live app or the Android UI. Formats reported by the
  Agent Device CLI differ from Apple platforms in ways unit tests cannot infer:
  `appstate` text uses `Foreground app:`, its JSON uses `package`, and snapshots
  contain no `Application` node.

## Android-specific hazards to re-check after UI-facing changes

These are device behaviors, not code paths, and no test enforces them:

- **The IME window reports as full-screen.** With the keyboard open, the CLI
  refuses ref taps as "covered by another visible element". Dismiss the keyboard
  first — but `keyboard dismiss` also closes an open picker, so a coordinate press
  is sometimes the only route.
- **Refs go stale quickly.** Resolve a ref and press it with no intervening
  snapshot; a rect can shift far enough to land a tap on a divider.
- **`scroll` granularity is unreliable** in virtualised lists. Prefer in-UI
  controls or `swipe` with explicit pixel distances.
- **`AGENT_DEVICE_DEVICE` doubles as an implicit `--device` selector.** It must be
  scrubbed from the environment for every CLI call except the session-creating
  `open`, or a bound session makes every later call fail `INVALID_ARGS`.
- **Never repeat an action with an unchanged failure signature.** Change a causal
  condition or escalate per `references/runner-recovery.md`.

## Release gate

Before publishing, confirm all applicable conditions:

- the user explicitly approved publication;
- the reported problem is fixed or the requested behavior is demonstrably present;
- deterministic tests and release hygiene pass, with the privacy scan **actually
  executed** rather than skipped;
- required physical-Android validation passes;
- no private paths, device serials, tokens, screenshots, or runtime artifacts are
  staged;
- installation guidance and public documentation match the candidate;
- upstream's `LICENSE` and `THIRD_PARTY_NOTICES.md` are still present and intact —
  MIT requires the copyright and permission notice to travel with the code;
- the working tree contains only intentional release changes.

After the gate passes:

1. Commit the reviewed candidate intentionally.
2. Push to this fork and require GitHub Actions to pass.
3. Merge to `main` only when the remote checks are green.
4. Create a new semantic version tag and GitHub release when versioning the fork.
   Use a patch version for compatible fixes, a minor version for new compatible
   capability, and a major version for breaking changes.
5. Verify the public repository, release URL, and installation path from the
   published tag.
6. Sync the approved published version to the local installed Skill with
   `sh deploy.sh` when needed.

Never move or silently rewrite an existing public tag. If a release has a problem,
preserve its history, mark it as superseded when appropriate, and publish a new
version.

## Evidence and privacy

Research screenshots are evidence, not release artifacts. They routinely contain
account tiers, balances, saved traveller profiles, and passport numbers.

- Never commit screenshots or evidence packs to this repository.
- Third-party personal data must be redacted even when the account holder consents
  to publishing their own — consent does not extend to other people appearing in
  the capture.
- Prefer a device with a throwaway profile when booking-funnel evidence needs to be
  shared.

## Communication defaults

Interpret common user language as follows:

- "Fix this" or "change this" means modify and test locally; do not publish.
- "Keep adjusting" means remain in local iteration.
- "I am satisfied" means the candidate may be considered accepted, but still do not
  publish unless the user also asks to publish.
- "Publish this version" or an equally explicit instruction authorizes the release
  workflow after the gates above pass.

At handoff, state whether the candidate is local-only, installed for testing, pushed
to a remote branch, merged to `main`, or released. Never leave the publication state
implicit.
