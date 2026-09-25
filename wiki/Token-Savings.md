# Projected token savings

The harness saves tokens on **reading and re-reading**: loading docs at session start, carrying context
between sessions, and auditing docs and code. Writing code costs what it did before. Jev's own cost is small
next to the model tokens it replaces (see [Measurements](Measurements)).

## Measured on one project

A Godot tactics game with about 170k tokens of design docs and 1,400 GDScript functions:

| Activity | Without | With | Saving |
|---|---|---|---|
| Loading docs at session start | ~170k | ~15–25k reading list | ~85–90% |
| Handover / context export | ~55k of conversation | ~5.6k digest | ~90% |
| Doc contradiction pass, after the first full review | re-read all docs | a few pairs per edited statement | ~99% per re-check |
| Code rule audit | read ~350k tokens of code | the report and the flagged functions | ~99%; an unchanged re-run costs $0 |

## First real milestone

A four-phase implementation milestone in the same project, one agent per phase, each given its own ~25k
reading list, against the nearest earlier milestone of the same shape run with the full read order. The tasks
and model versions differ, so treat the ratios as indicative:

| | Earlier milestone (full read order) | With reading lists | Change |
|---|---|---|---|
| Agent turns | 911 | 599 | −34% |
| Context carried per turn (median / peak) | 365k / 914k | 291k / 506k | −20% / −45% |
| Cache reads (76–86% of the bill) | 397M | 170M | −57% |
| Fresh context written | 1.94M | 1.91M | flat |
| Cost at the same model rates | ~$94 | ~$45 | about half |

The saving did not come from loading less: agents loaded code instead of docs, so fresh context stayed flat.
It came from fewer turns and a smaller context carried through each one. Reading-list misses: 54 sections
opened beyond the lists, 29 of them code, which is what `ctx find --code` now covers.

## Projecting it for your repo

Two numbers decide most of it: **D**, the tokens of docs a session would otherwise read (`jeverifier ctx index <repo>`
lists every doc section with its size), and **B**, the reading-list budget of `ctx find` (25k by default).

| Activity | Tokens without | Tokens with | Notes |
|---|---|---|---|
| Session start | D | about B, plus the files always loaded | nothing saved when D is at or below B |
| Handover | the conversation you would carry over | about a tenth of it | a digest quotes decisions, preferences, open items and status changes |
| Doc consistency re-check | about D, plus the reasoning over it | a few pairs per edited statement | the first full review costs about as much as one careful read |
| Code audit | about (characters of code) ÷ 4 | the report | the first run sends every function to Jev; later runs only changed ones |

## Worked examples

Estimates from the formulas above, for one session start plus one handover:

| Repo | Docs (D) | Session start | Handover (55k conversation) | Saved per session |
|---|---|---|---|---|
| Small | 20k | 20k → 20k | 55k → ~6k | ~50k (≈65%) |
| Medium | 80k | 80k → ~25k | 55k → ~6k | ~105k (≈77%) |
| Large | 170k | 170k → ~25k | 55k → ~6k | ~195k (≈86%) |

Over a milestone of 20 sessions in the large repo, that is roughly 4M tokens of reading not done, before
counting audits. The audits matter in a different way: a full doc or code audit becomes cheap enough to run
every session instead of rarely.

These are projections, not guarantees. Recall is imperfect: a reading list can miss a section the task needs
(Claude then opens it, which costs tokens back), and a digest can leave a turn out. Measure on your own repo
with `jeverifier wiki selftest` and by comparing a few sessions with and without the reading list.

## Related pages

- [Measurements](Measurements)
- [How it works](How-It-Works)
- [Overview](Overview)
