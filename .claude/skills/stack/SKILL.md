---
name: stack
description: Run and inspect the local pieces of Guardana — the throwaway PostgreSQL for the collector, the collector itself, a fake OpenAI-compatible endpoint to probe, the documentation site served locally, the two container images. Use to try a command for real, to reproduce a collector or probe problem, or before a browser check.
argument-hint: "[postgres | collector | endpoint | site | images]"
---
# Local stack

Requested: $ARGUMENTS (nothing = `postgres`).

| what | command | notes |
|---|---|---|
| postgres | `docker compose -f deploy/docker-compose.dev.yml up -d --wait` | port **55439** on purpose; databases `guardana_test` (the suite) and `guardana` (local use). Tests read `GUARDANA_TEST_DATABASE_URL=postgresql://guardana:guardana@127.0.0.1:55439/guardana_test`; `GUARDANA_REQUIRE_POSTGRES=1` turns the skip into a failure, as CI does. |
| collector | `export GUARDANA_DATABASE_URL=postgresql://guardana:guardana@127.0.0.1:55439/guardana` then `uv run guardana-collector migrate` and `uv run guardana-collector serve` | migrations never run on container start; `docs/usage-collector.md` has the token and environment model. The engine reaches it only through `--reporter server://…`. |
| endpoint | a fake OpenAI-compatible server is a few lines of `http.server` answering `/v1/chat/completions`; `guardana.core.testing` has scripted transports for in-process use | `uv run guardana probe --url http://127.0.0.1:<port>/v1 --model fake …` then read the JSON it wrote. `plan probe` never contacts the endpoint. Never point `probe`, `monitor` or `calibrate` at a paid provider without the user saying so and a budget. |
| site | `uv run python scripts/build_site.py && python3 -m http.server -d site 8099` | exactly what Cloudflare serves; `site-check` for what to look at. |
| images | `uv run --no-project python scripts/image_smoke.py` (`--no-build` reuses images) | builds `guardana-cli:smoke` and `guardana-collector:smoke` and runs them; needs docker; no argument parser, so no `--help`. |
| deps | `uv sync` (all five packages plus dev and docs groups) | `uv sync --locked` is what CI runs. |

Nothing here contacts a network host other than what you started; the product's rule is the
only traffic is to the target under test.
