---
name: release
description: Cut a Guardana release without repeating the mistakes previous releases made — a tag pushed before CI was green, a stale cache that hid a red build, a manual doc step nobody remembered, a script that runs the whole gate when asked for --help. Use when asked to release, tag, publish or bump a version.
argument-hint: "[patch | minor | major | X.Y.Z]"
---
# Cutting a release

Part: $ARGUMENTS. `RELEASING.md` is the runbook and it is correct. This is the part that is about
what has actually gone wrong, three times.

## The order that matters

**Never push the branch and the tag together.** Pushing the tag starts the PyPI publish, which
waits on the `pypi` environment for a human approval click. If CI on the same commit then turns
red, the maintainer has to cancel a run that is already waiting, fix, re-tag, and approve a
*second* time — and the cancelled run stays in the history looking like a failed release.
Worse: **cancelling does not undo an upload.** A cancelled Release run has already published two
of the five packages from a red commit. Do not move a tag after anything has been published.

So:

1. `scripts/ci_local.sh --quiet` — every CI job including the clean-install check, the SBOM
   check and the image smoke; read every verdict line, nothing NOT RUN;
2. bump, regenerate, roll the changelog, commit;
3. **push `main` only** (the hook checks the site is in sync — the push deploys it);
4. wait for CI to conclude **green on that exact commit** — read the steps, not the job;
5. only then push `vX.Y.Z` and the moving `vX.Y` (the hook asks before any tag push).

`scripts/release.py <part>` does 1–5 in that order and refuses to push the tag when it cannot
check CI — "could not tell" is treated as "no". It has **no `--help`**: `--help` is read as a
version, it fetches from `origin` and runs the whole gate. Preview with `--dry-run`.

## Before the bump

`bump_version.py` rewrites every pin and version marker it can discover, and it refuses to run
if a required marker has gone missing. What it cannot write is prose:

- **`ROADMAP.md`** — "What ships today (X.Y.Z)", and delete what shipped from the milestone;
- **`CHANGELOG.md`** — the `[Unreleased]` heading rolled to
  `## [X.Y.Z] - DATE — <one line saying what this release is>`; `release.py` has lost the
  title before, check it after running.

Then the five documentation places (`/docs`) once more for the release as a whole, and
`generate_docs.py`, `sync_site.py`, `build_site.py`, `generate_llms_txt.py` — each has `--check`
and each is a CI gate.

## Never attribute anything to an AI

No `Co-Authored-By:`, no "generated with", no AI name in a commit message, a tag message, a PR
body or a release note. Check the last line of the message rather than assuming.

## After the tag

Verify against PyPI's API rather than from memory — all five packages, at the new version — and
`ghcr.io` for both images. A release is not done because the workflow went green; it is done
when the artifacts are there. After the **first** release that pushes images, make the two
packages public (`docs/maintainers/github-setup.md`); verify with `docker logout ghcr.io` first.
Then `docs/work/` is empty, the work files are closed, and `ROADMAP.md` no longer lists what
just shipped.
