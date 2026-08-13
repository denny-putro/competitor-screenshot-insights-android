# Competitor Screenshot Insights maintenance agreement

This file applies to the entire repository. Treat this repository as the canonical source for public Skill code. Treat `$CODEX_HOME/skills/competitor-screenshot-insights` as a runtime deployment or test candidate, not as an independent source of truth.

## Default rule

A bug report or change request authorizes local diagnosis, modification, and testing only. It does not authorize a push, pull request, merge, tag, GitHub release, or replacement of an existing public release.

Publish only after the user explicitly says the candidate is satisfactory and asks to publish it. If the instruction is ambiguous, keep the work local and report what remains to be verified.

## Iteration workflow

1. Preserve `main` and existing release tags while experimenting. Start a local `codex/<topic>` branch from the current public baseline.
2. Reproduce or characterize the reported behavior before changing it. Record the actual failure evidence rather than relying only on a proposed diagnosis.
3. Make intentional edits in this repository. Never copy an installed Skill wholesale back into the repository; selectively port reviewed changes so private configuration, state, screenshots, recordings, caches, and device identifiers cannot enter the public source.
4. Add or update a regression test for a defect whenever the behavior can be tested deterministically.
5. Run validation appropriate to the change. Iterate locally until the candidate is satisfactory.
6. When real-device validation is required, deploy the candidate to the local installed Skill only as a reversible test step. Preserve a known-good public tag or clean copy so the installed Skill can be restored. Do not treat this deployment as publication.
7. Report the result and wait for user acceptance. Continue editing when the user is not satisfied.
8. Enter the release workflow only after explicit publication approval.

## Validation policy

- For any Skill change, run `sh skills/competitor-screenshot-insights/scripts/run-tests.sh` and `sh scripts/release-check.sh`.
- For capture, navigation, target identity, scrolling, popup, advertisement, horizontal-container, or Runner behavior, also validate the affected journey on a physical iPhone. Confirm the original failure is gone and preserve evidence of the result.
- For installation, setup, preflight, path, dependency, or packaging changes, validate both a new-user `setup_required` path and an existing-user cached `ready` path. Also test the GitHub archive installation mode where executable bits are absent.
- Documentation-only changes do not require phone operation, but still require release hygiene and relevant structure/link checks.
- A passing test suite is necessary but does not replace real-device validation for behavior that depends on a live App or iPhone UI.

## Release gate

Before publishing, confirm all applicable conditions:

- the user explicitly approved publication;
- the reported problem is fixed or the requested behavior is demonstrably present;
- deterministic tests and release hygiene pass;
- required physical-iPhone validation passes;
- no private paths, signing values, device identifiers, tokens, screenshots, or runtime artifacts are staged;
- installation guidance and public documentation match the candidate;
- the working tree contains only intentional release changes.

After the gate passes:

1. Commit the reviewed candidate intentionally.
2. Push a release branch or the approved change to GitHub and require GitHub Actions to pass.
3. Merge to `main` only when the remote checks are green.
4. Create a new semantic version tag and GitHub release. Use a patch version for compatible fixes, a minor version for new compatible capability, and a major version for breaking changes. Keep the beta suffix while the project remains in public beta.
5. Verify the public repository, release URL, and Skill Installer path from the published tag.
6. Sync the approved published version to the local installed Skill when needed.

Never move or silently rewrite an existing public tag. If a release has a problem, preserve its history, mark it as superseded when appropriate, and publish a new version.

## Communication defaults

Interpret common user language as follows:

- “Fix this” or “change this” means modify and test locally; do not publish.
- “Keep adjusting” means remain in local iteration.
- “I am satisfied” means the candidate may be considered accepted, but still do not publish unless the user also asks to publish.
- “Publish this version” or an equally explicit instruction authorizes the release workflow after the gates above pass.

At handoff, state whether the candidate is local-only, installed for testing, pushed to a remote branch, merged to `main`, or released. Never leave the publication state implicit.
