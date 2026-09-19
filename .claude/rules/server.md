---
paths:
  - "packages/guardana-server/**"
  - "deploy/**"
---
# The collector (`guardana-server`) and deployment

Why: `docs/maintainers/lessons.md` § Collector. Designs: `docs/design/collector-*.md`.

- **Tenancy and authorization are part of done.** Every route and every query answers "does
  this leak across organizations" before it is finished, not in a later hardening pass. A
  pinned key writes and reads only its environment.
- **The collector consumes the versioned envelope** (`schema_version`) through the `Reporter`
  seam and never imports the engine; the mirror contract in `pyproject.toml` fails the build
  either way. It is optional in every direction: no feature requires it.
- **Redact on ingest**, before persistence or queuing; retention, deletion and audit behaviour
  have their own design documents and tests.
- **PostgreSQL tests** skip locally without `GUARDANA_TEST_DATABASE_URL` and refuse to skip in
  CI (`GUARDANA_REQUIRE_POSTGRES=1`, `GUARDANA_REQUIRE_PG_TOOLS=1`). Start
  `deploy/docker-compose.dev.yml` (port 55439); `scripts/ci_local.sh` does and sets the
  variables. The backup/restore test needs `pg_dump` at the server's major version (16).
- **Migrations never run on container start**; `guardana-collector migrate` is a deliberate
  step. `deploy/docker-compose.yml` takes every secret from the `.env` beside it, copied from
  `deploy/env.example` (gitignored, never printed) and binds the collector to loopback — the operator fronts it with TLS.
- Image references (`ghcr.io/guardana/guardana-collector:X.Y`) are rewritten by
  `bump_version.py`; a pin discovered by hand sits on an old tag for releases before anyone
  notices, so `test_no_tracked_file_pins_a_version_from_another_series` scans for them.
- The CI templates under `deploy/ci/` run the published image, not this tree; a template is a
  user's first contact with exit codes and `--user`, and `test_ci_templates.py` pins them.
