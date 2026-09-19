---
name: site-check
description: Check the landing page and the generated documentation site (site/, guardana.dev) in a real browser — confirm a page renders after a docs change, review it at phone width, read the console and network for anything that contradicts the no-telemetry promise, collect screenshots as evidence. Use after any change under site/, docs/ or scripts/sitegen/, and before a push that deploys the site.
argument-hint: "[page or path] [local | live]"
---
# Site check in a real browser

Target: $ARGUMENTS

Delegate the clicking to the `browser` agent (page snapshots are large); keep its findings here.
Tools: the Playwright MCP (`browser_navigate`, `browser_snapshot`, `browser_resize`,
`browser_console_messages`, `browser_network_requests`, `browser_take_screenshot`).

## Serve it locally — what Cloudflare serves, byte for byte

```bash
uv run python scripts/build_site.py            # rebuild site/docs/ from docs/ (or --check)
python3 -m http.server -d site 8099            # http://localhost:8099/
```

| page | what to check there |
|---|---|
| `/` | the landing page: the counts (`sync_site.py --check` says they are current), the terminal demo, every link resolves |
| `/docs/` | the documentation home: the sidebar mirrors `docs/index.md`, every section has its pages |
| `/docs/usage-scan.html` (any usage page) | fenced commands render as code, tables fit at 400 px, the status badge matches the page's front matter |
| `/docs/generated/rule-catalog.html` and one rule page from the explorer | the rule count, taxonomy links, no "do not edit" marker leaking into the page |
| `/docs/design/<any>.html` | the status word matches the document's `**Status:**` line |

Live (`https://guardana.dev`): look only. There is nothing to log into and nothing to submit.

## What a pass covers

1. The page renders with its real content — no empty section, no raw markdown, no missing
   generated block. A blank where a count belongs is a finding, not an empty state.
2. Console errors and failed requests after each page. **Any request to a host other than the
   page's own is a finding**: the site promises no telemetry and ships a closed
   Content-Security-Policy in `site/_headers`.
3. Desktop and **400 px**: nothing cut off, no horizontal page scroll, code blocks scroll
   inside themselves, the sidebar collapses.
4. Keyboard: links reachable in order, visible focus.
5. Screenshots of the changed pages (before/after when fixing a bug) saved to the scratchpad;
   attach the paths to the report, and to the commit body when they are evidence.

A site change is not done until `uv run python scripts/build_site.py --check` and
`uv run python scripts/generate_llms_txt.py --check` are clean — the hook refuses a push to
`main` otherwise, because the push is the deploy.
