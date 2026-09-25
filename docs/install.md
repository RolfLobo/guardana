---
title: "Installing"
nav_order: 30
summary: "installing the CLI"
status: stable
---

# Installing Guardana

Guardana requires **Python 3.11+**.

## Install from source (recommended today)

Clone the repository and use [`uv`](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/guardana/guardana
cd guardana
uv sync                  # resolves the full workspace (5 packages) + dev tooling
uv run guardana --version
uv run guardana scan examples/vulnerable-model   # exits 1: finds the planted issues
```

Inside the checkout, `guardana scan .` exits `1` because `examples/vulnerable-model/` contains planted issues. In your own project, `guardana scan .` scans the current directory.

`uv sync` installs `guardana-core`, `guardana-rules`, `guardana-cli`, `guardana-report`, and `guardana-server` from the root `pyproject.toml`, plus `ruff`, `mypy`, and `pytest`. Run commands with `uv run guardana ...` inside the checkout. See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for contributor setup and test/lint gates.

## Install from PyPI

All five packages are on PyPI (Apache-2.0). Install the CLI with any of these commands:

```bash
uvx --from guardana-cli guardana scan .   # zero-install run
uv add guardana-cli                       # or add it to a project
pip install guardana-cli                  # or plain pip
```

The `guardana` console script comes from `guardana-cli`, which installs `guardana-core`, `guardana-rules`, and `guardana-report`. Use `--from guardana-cli` so `uvx` finds the script. The optional collector has a separate install: `pip install guardana-server`.

Run the Git repository with `uvx`:

```bash
uvx --from git+https://github.com/guardana/guardana#subdirectory=packages/guardana-cli guardana scan .
```

## Run it as a container

The CLI and collector images are available from GitHub Container Registry:

```bash
docker run --rm -v "$PWD:/work:ro" ghcr.io/guardana/guardana:0.28 scan /work
docker run --rm ghcr.io/guardana/guardana-collector:0.28 --help
```

Tags include the exact version, the moving minor used above, and `latest`. Pin the moving minor in CI to receive fixes without changing the rule set. Both images run as a non-root user, support `linux/amd64` and `linux/arm64`, and include an SBOM and signed provenance attestation. See [`deploy/docker/README.md`](../deploy/docker/README.md) for mounts, exit codes, reports, and image builds.

## The optional collector

`guardana-server` is a separate service. `scan`, `probe`, and `monitor` do not require it. Install it to collect findings centrally; see [`architecture.md`](architecture.md#the-coreserver-boundary).

```bash
pip install "guardana-server[serve]"   # `[serve]` adds the ASGI server
guardana-collector migrate             # then: guardana-collector serve
```

The `[serve]` extra adds an ASGI server. Deployments using gunicorn or hypercorn can omit it. See [`usage-collector.md`](usage-collector.md) for collector use and [`deployment.md`](deployment.md) for production deployment.

## Installing a third-party rule package

Install third-party rule/evaluator packages as Python dependencies:

```bash
uv add acme-guardana-rules   # example; see examples/custom_rule/
```

Guardana discovers installed rules through the `guardana.rules` entry point (see [`extending.md`](extending.md)). These packages execute code, so install only packages you trust. Use `--plugins builtins` to allow only Guardana's reviewed rules; see [`SECURITY.md`](../SECURITY.md).
