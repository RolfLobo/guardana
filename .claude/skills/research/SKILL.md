---
name: research
description: Research a roadmap question before anyone plans or builds it — a milestone item, a standard or framework update (OWASP LLM/ASI, MITRE ATLAS, NIST, OTLP GenAI conventions), a competitor's move, a user problem, a "should we". Produces cited evidence, options with trade-offs and a recommendation that lands as a proposed design document or a ROADMAP edit, never as more prose. Use for "zbadaj", "research", "czy warto", "co robi konkurencja", "what would it take".
argument-hint: "[question, roadmap item or exit criterion]"
---
# Research — evidence, then a recommendation

Question: $ARGUMENTS

Working file: `docs/work/research-<slug>.md` (in flight, not published; delete or park it when
the conclusion has landed). Under 200 lines. English.

## 1. Frame it against the plan

- Which `ROADMAP.md` item or exit criterion does this touch, and which decision does the answer
  change? If none — say so; research with no decision attached is a reading list.
- Check the non-goals and the product principles in `CLAUDE.md` first. A question whose every
  answer breaks a principle (an inline proxy, a phone-home, a vendor name in the engine) is
  answered by the principle.
- Check what already exists: `docs/design/` (an accepted design may be waiting), `CHANGELOG.md`,
  `docs/work/BACKLOG.md`, `FEATURES.md`. Shipped or superseded → say so and stop cleanly.

## 2. Gather evidence, cheapest source first

| source | how | rule |
|---|---|---|
| this repository | `scout` for "where does X live / how is Y done today" | `path:line`, never memory |
| standards and frameworks | `WebSearch` / the `web-fetch` agent on the primary source (owasp.org, atlas.mitre.org, nist.gov, opentelemetry.io) | URL + the date you read it; quote the clause, not a summary of it |
| competitors and market | the project's own docs and repos, release notes, pricing pages | what they DO, verified on the page; a claim you could not verify is marked `UNVERIFIED` |
| users | issues, discussions, the audit in `docs/design/audit-0.23-market.md` | a quote beats a paraphrase |
| a second and third opinion | `text-broker` with `--engine both` — "what would you build, what breaks, what is missing" | model output is an opinion to check, not evidence; a disagreement between the two families is a finding in itself |

Every count comes from a source that measured it, every capability claim from a page that
states it — principle 9 applies to research the same as to the README.

## 3. Write it down

Sections of the working file: **Question and the decision it informs** · **What exists today**
(with anchors) · **Evidence** (one bullet per fact, with its source) · **Options** (two to four,
one paragraph each: what it is, what it costs, which principle or exit criterion it serves or
strains) · **Recommendation** (one option, why, what it moves in the roadmap and what it defers,
with the reason) · **Open questions** (the user's to answer, each with a default) ·
**Sources**.

## 4. Land it

- A new capability or a change of shape → a design document under `docs/design/`, named for
  its topic, `**Status:** proposed`, with the losing options kept (the README there is the
  convention; `docs/index.md` gets the entry, `scripts/build_site.py --check` proves the page
  renders).
- A change of order or scope → an edit to `ROADMAP.md`: delete what shipped, add what this
  defers with the reason, move an item with a one-line justification. New work is not
  prioritised by adding prose — `ROADMAP.md` says so itself.
- No change → the working file's conclusion goes into the commit message or an issue; the
  file is deleted.

## Report

The question, the recommendation in two sentences, the strongest evidence for and against, the
sources, what the user must decide, and what was NOT verified.
