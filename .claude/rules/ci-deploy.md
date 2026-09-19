---
paths:
  - ".github/**"
  - "action.yml"
  - ".pre-commit-config.yaml"
  - "wrangler.jsonc"
---
# CI, the release pipeline and the site deploy

Runbook: `RELEASING.md`; the order that has gone wrong: the `release` skill.

- **Every action is pinned by commit SHA** with a version comment, and every workflow declares
  least-privilege `permissions`. A too-wide token never fails a build, which is why it is
  written down instead of defaulted.
- **`ci.yml` runs on every push and PR**: the gate on three Python versions against a real
  PostgreSQL (`GUARDANA_REQUIRE_POSTGRES=1` — the skip is a failure there), `uv audit`, the
  dogfood scan, the two container images, the clean-install check, the SBOM check and the three
  isolated example suites. `scripts/ci_local.sh` mirrors it; keep them in step in the same change.
- **`release.yml` runs on `v*.*.*` tags only**: clean install → build the five distributions →
  SBOM per distribution → provenance → PyPI through the `pypi` environment's approval click →
  both images (amd64, arm64) → the GitHub Release from the changelog section. The moving `vX.Y`
  tag is for the Marketplace Action and never re-triggers a publish.
- **A push to `main` deploys `site/`** through Cloudflare's `npx wrangler deploy`, from the
  tree, before CI has run: `wrangler.jsonc` is a static-assets Worker with no build step,
  `workers_dev` and previews off. The pre-push hook refuses a push while the generated site is
  stale.
- **`action.yml` is a public contract**: its inputs and its `version` default (rewritten by
  `bump_version.py`) are pinned by `test_release_tooling.py`; it installs `guardana-cli` from
  PyPI at run time and uploads SARIF to code scanning.
- **`.pre-commit-config.yaml` is CI's local twin**: fast checks on commit, the slow ones on
  push, conventional-commit messages enforced on `commit-msg`. A hook added to CI gets its
  local counterpart in the same change.
- A workflow's job conclusion is not the verdict: read the failing **step**. A cache-cleanup
  step has gone red while every test step passed.
