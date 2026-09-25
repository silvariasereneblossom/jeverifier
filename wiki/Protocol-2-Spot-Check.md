# Protocol 2: Spot-Check

Find statements in the docs that contradict each other. Jev ranks candidate pairs cheaply; Claude
reviews the short list and decides; every decision is recorded so the next run is better.

## Trigger

"Run Protocol 2" or "Spot-check".

## Procedure

1. **Rank:** `jeverifier wiki check <repo>`. It extracts claims (sentences with a number or a rule
   word) and keeps only sections describing the project *as it is now* (history and plans are
   expected to differ). It writes two lists to `out/<repo>/consistency-<date>.md` in the jeverifier checkout:
   - **Number mismatches:** code finds statements counting the same thing with different numbers;
     Jev judges whether they count the same specific thing.
   - **Other possible contradictions:** pairs grouped by topic or close wording, ranked by Jev's
     contradiction score.

   **First run (no baseline):** the full ranking — top 50 number mismatches and top 130 others,
   about 20k tokens to read. This is the expensive pass: most pairs are false alarms, and recording
   them is what makes later runs cheap.
   **Every later run (delta):** only pairs touching a statement that is new or changed since the
   last `accept`, above a score floor — typically 3–4 pairs per edited statement. `--deep` shows the
   full ranking again when you want to dig further.
2. **Review each pair** and record a verdict:
   `jeverifier wiki verdict <repo> <id> contradiction|stale|false-alarm --note "why"`
   - **contradiction:** both describe the current state and disagree — fix it (steps 4–5).
   - **stale:** one side is out of date — fix that side.
   - **false-alarm:** different things, or not actually in conflict. The pair is hidden from future
     runs until either statement's text changes.
3. **Sample 10 more section pairs yourself**, preferring different documents about the same
   subsystem. The ranked list does not see contradictions *inside* one section (a count and the list
   right after it) or statements without a number or rule word.
4. **Verify** anything not obvious with Protocol 3; the code and the check scripts are the truth.
5. **Fix**, re-run `check` (the fixes are new text, so their pairs appear in the delta), review those.
6. **Accept:** `jeverifier wiki accept <repo>` records the reviewed text as the baseline
   (`docs/wiki/checks/baseline.json`, versioned). The next `check` should list 0 pairs until the docs
   change. Use `--git-ref HEAD` to accept the committed text when the review covered that.
7. Log the findings (Protocol 5) and commit (Protocol 7), including `docs/wiki/checks/`.

## Making the filter better over time

- **Verdicts** live in `docs/wiki/checks/verdicts.jsonl`, versioned with the docs.
- **Section kinds:** if sections are filtered wrongly (history labelled current, or the reverse), correct
  them in `docs/wiki/checks/kinds.json`: a folder or file prefix covers everything under it
  (`"docs/contracts/": "history"` for archived contracts), and an exact `"<file>#<heading path>"` entry
  overrides a prefix for one section.
- **Budget:** `check` and `selftest` estimate each paid stage before sending it and stop at `--max-cost`
  (default $1). Tags, section labels and pair judgments are cached by text, so an unchanged re-run is free
  and a run cut short keeps what it already paid for.
- **Measure, don't assume:** `jeverifier wiki selftest <repo>` plants two kinds of contradiction in a
  scratch copy (a changed count; a flipped rule word such as never → always) and reports, per plant,
  both texts, its rank in each list, and why it was missed if it was. Read the plant texts before
  trusting the figure. Run it after changing anything above, and now and then as the docs grow.
  Measured on a game project with ~170k tokens of docs (2026-09-24): full lists — numbers 6/10 (an upper bound: the plants
  follow the number check's own rule), rules 4/4 valid plants; delta mode — numbers 8/10, rules 4/4,
  with 55 pairs listed for 15 edited statements. The first review of the full lists found 10 real
  stale statements in 175 pairs. A strong lead list, not coverage — step 3's sampled pairs stay.
- Re-runs only pay Jev for claims and sections whose text changed (cached by text hash).
