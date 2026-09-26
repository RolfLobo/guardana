---
name: content-model
description: Route wording work to GPT (codex CLI) or Gemini (agy CLI) instead of writing it with Claude — landing-page copy, a readability rewrite of a README or docs page, attack and judge prompts for a rule, release-note phrasing, and any verdict about such text (which sentences are stale, which draft reads better, is this page clear). Use whenever a task would produce or judge prose a reader of this project sees.
argument-hint: "[task]"
---
# Wording goes to the text models

Task: $ARGUMENTS

**Rule.** Claude is the engineer here. Technical documentation that restates the code — a flag,
an exit code, a schema field, a command's behaviour — is written here, from the code. Prose whose
value is in the wording — how the landing page sells, whether a page is clear, the phrasing of a
release note, the text of an attack or judge prompt inside a rule — and every verdict ABOUT such
prose comes from GPT or Gemini. Claude prepares the job, checks the SHAPE of the answer and
wires it in through the normal gates.

## The door

```bash
uv run python scripts/text_model.py --detect          # {"gpt": path|null, "gemini": path|null}
uv run python scripts/text_model.py --prompt P.md --input page.md --out out.json \
    --schema S.json --engine gpt|gemini|both|auto --effort low|medium|high
```

- `gpt` → `codex exec`, read-only sandbox, empty working dir, the user's configured GPT model
  (`TEXT_MODEL_GPT` overrides). `gemini` → `agy --print`, Gemini Pro (`TEXT_MODEL_GEMINI`
  overrides; non-Gemini ids are refused). `auto` = GPT if installed, else Gemini.
- `both` writes `out.gpt.json` and `out.gemini.json`. Use it for any verdict that would CUT,
  REJECT or REWRITE something: only what both families asked for stands; disagreements are
  reported with both reasons.
- **Neither CLI installed (exit 3): stop and say so.** Do not fall back to writing it yourself.
  Leave the sentence as it is and report the gap.

## Cost discipline

Each call boots a whole agent session on the other side — several thousand tokens of overhead
before your prompt, on the user's GPT/Gemini subscription. So: one call per BATCH (10–30 pages,
sentences or prompts, JSON in / JSON out), never one per item; `--effort low` for mechanical
work, `medium` by default, `high` for a judgement about a whole page. Before more than 5
calls, tell the user how many calls and which engine, and wait.

## A job that works

1. **Prompt file** (scratchpad or `cache/text/`): who reads this project's pages (an engineer
   evaluating a security tool, reading on GitHub or guardana.dev), the task, hard rules, the
   output shape, one or two examples of GOOD output. Rules worth stating every time: every path,
   flag, command, count, rule id, version and link is copied byte-identical; no new capability
   claim, no number the input did not contain, no future tense about features; English; short
   sentences; the answer first.
2. **Inputs as files** (`--input`): the page or prompts to work on, the neighbouring pages it
   must not repeat, `FEATURES.md` when the model must know what exists.
3. **Schema** whenever code or a checklist consumes the answer. Closed objects only
   (`additionalProperties: false`, every property in `required`).
4. **Validate mechanically**: parses, one answer per input id, every code span / path / count /
   link present in the input still present in the output, length caps hold. Re-ask once quoting
   the failure; then mark the item failed. Taste is not yours to apply — a doubtful sentence
   goes to the second engine or to the user.
5. **A rewrite of an existing page is compared with `git show main:<path>`** before it is wired
   in, and with the `--input` file too when the page was edited before it was sent. List every
   fact the base states that the rewrite dropped — a flag, an exit code, a default value, a
   maturity caveat, an item of a list of what a command does. A dropped fact returns in its
   original sentence, byte-identical, unless the brief removed it on purpose; it is never
   re-worded here. A code block left without a sentence that introduces it is re-asked once with
   the block quoted, then marked failed. No base to compare with (a new or renamed page) is
   stated in the report, never skipped silently. The code-span check in step 4 does not catch
   any of this: it lives in prose.
6. **Wire it in through the gates**: a docs page through `test_docs_consistency.py` and
   `build_site.py --check`; the landing page through `sync_site.py --check` and
   `test_landing_page.py`; a rule's prompts through its positive, negative and inconclusive
   fixtures (`guardana rule test`).

For more than a couple of calls, delegate the whole job to the `text-broker` agent and keep only
its file paths and counts in this context.
