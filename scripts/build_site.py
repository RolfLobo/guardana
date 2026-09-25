"""Render the documentation site into `site/docs/`, and publish `schemas/` into `site/schemas/`.

    uv run python scripts/build_site.py            # write site/docs/ and site/schemas/
    uv run python scripts/build_site.py --check    # exit 1 if stale; write nothing

The same pair of guards `generate_docs.py`, `sync_site.py` and
`generate_llms_txt.py` already have: `release.py` runs the first and
`test_documentation_site.py` runs the second, so a page edited without rebuilding
turns the suite red rather than waiting for somebody to cut a release.

`wrangler.jsonc` stays a static-assets-only Worker with no build command — what
Cloudflare serves is what is committed here, which is also what a reviewer can
read in a diff. Two things follow, and both are deliberate:

- **Nothing under `site/docs/` is edited by hand.** The whole tree is deleted and
  rewritten, so a hand-edit is silently lost — which is the honest outcome, since
  the markdown is the source.
- **No script is emitted anywhere.** `site/_headers` ships `script-src 'none'`,
  and that is a claim a visitor checks in devtools rather than a default nobody
  chose. Filtering the rules is navigation between pre-rendered pages.
- **Every schema is served at the URL its `$id` names.** A validator that
  dereferences the `$id` gets the same bytes as `schemas/`; a schema whose `$id`
  is not under `https://guardana.dev/schemas/` fails the build.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_OUT = _REPO / "site" / "docs"
_SCHEMAS = _REPO / "schemas"
_SCHEMAS_OUT = _REPO / "site" / "schemas"
_SCHEMA_BASE = "https://guardana.dev/schemas/"
_SCHEMA_PATH = re.compile(r"[a-z][a-z0-9-]*/v[1-9][0-9]*\.schema\.json")

sys.path.insert(0, str(_REPO / "scripts"))
sys.path.insert(0, str(_REPO / "packages" / "guardana-core" / "src"))
sys.path.insert(0, str(_REPO / "packages" / "guardana-rules" / "src"))

from guardana.core import __version__  # noqa: E402

from sitegen import SiteBuildError, build  # noqa: E402

_NAMED = 8
"""How many stale paths `--check` prints before it stops listing them."""


def _published_schemas() -> dict[str, bytes]:
    """Map every schema in `schemas/` to the path its `$id` names, byte for byte."""
    published: dict[str, bytes] = {}
    for source in sorted(_SCHEMAS.glob("*.schema.json")):
        body = source.read_bytes()
        schema_id = json.loads(body).get("$id")
        relative = schema_id.removeprefix(_SCHEMA_BASE) if isinstance(schema_id, str) else ""
        if not isinstance(schema_id, str) or not _SCHEMA_PATH.fullmatch(relative):
            raise SiteBuildError(
                f"schemas/{source.name}: `$id` must be {_SCHEMA_BASE}<kind>/v<N>.schema.json, "
                f"got {schema_id!r}"
            )
        if source.name != relative.replace("/", "-"):
            raise SiteBuildError(
                f"schemas/{source.name}: file name disagrees with `$id` {schema_id}"
            )
        if relative in published:
            raise SiteBuildError(f"schemas/{source.name}: `$id` {schema_id} is claimed twice")
        published[relative] = body
    if not published:
        raise SiteBuildError("schemas/ holds no *.schema.json to publish")
    return published


def _on_disk(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _write(root: Path, files: dict[str, bytes]) -> None:
    """Replace the tree wholesale, so a renamed page cannot leave its old URL live.

    A page deleted from `docs/` but left in `site/docs/` would keep answering, and
    stale documentation that still loads is worse than a 404: nothing tells the
    reader they are looking at something that no longer describes the product.
    """
    if root.exists():
        shutil.rmtree(root)
    for relative, content in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def main() -> int:
    """Build the site, or report which pages on disk no longer match the sources."""
    parser = argparse.ArgumentParser(description="Render docs/ into site/docs/.")
    parser.add_argument("--check", action="store_true", help="exit 1 if stale; write nothing")
    args = parser.parse_args()

    try:
        pages = build(_REPO, __version__)
        trees = {
            _OUT: {name: body.encode("utf-8") for name, body in pages.items()},
            _SCHEMAS_OUT: _published_schemas(),
        }
    except SiteBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stale_trees = 0
    for root, files in trees.items():
        label = root.relative_to(_REPO).as_posix()
        current = _on_disk(root)
        if current == files:
            print(f"{label} is current ({len(files)} files)")
            continue
        if args.check:
            stale = sorted(set(files) ^ set(current)) or sorted(
                name for name, body in files.items() if current.get(name) != body
            )
            named = ", ".join(stale[:_NAMED])
            print(f"{label} is out of date: {named}{' …' if len(stale) > _NAMED else ''}")
            stale_trees += 1
            continue
        _write(root, files)
        print(f"wrote {len(files)} files to {label}")
    if stale_trees:
        print("run `uv run python scripts/build_site.py` to rebuild it")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
