# How the coding harness works

Every part follows one pattern: **code finds candidates, Jev ranks or labels them, Claude reviews the short
list, and the review is recorded** so the next run shows only what changed. Jev answers are cached by the
text they judged, so an unchanged re-run costs nothing, and a run cut short keeps what it already paid for.
Paid runs stop before they would pass `--max-cost` (default $1).

## Loading context: `ctx find`

A fresh session in a docs-heavy repo would read every design doc. `ctx find <repo> "<task>"` splits the
Markdown docs into sections, asks Jev which sections the task needs, and returns a reading list inside a
token budget (default 25k). The files a session always loads (`CLAUDE.md`, a handover) are listed but not
scored. The list is a starting point: Claude still opens anything the task turns out to need, and always
the code for any API the task pins, since the ranker reads docs, not function signatures.

## Exporting context: `ctx digest` and session logs

`ctx digest <session>` reads a Claude Code transcript, drops tool output, and has Jev triage each
conversational turn into **decisions, standing preferences, open items and status changes**. The digest
quotes those turns verbatim, trimmed, newest last; Jev only chooses, so nothing in it was paraphrased.
`wiki log` turns a digest into a dated session log under `docs/wiki/sessions/` (Protocol 5), which the next
session reads instead of the transcript. Session logs quote the user, so they are marked internal and never
mirrored.

## Keeping docs consistent: `wiki check`

1. **Statements.** Every sentence with a number or a rule word (*must, never, always, only, at most*…), with
   its file and line.
2. **Topics.** The docs' own headings, near-duplicates merged; Jev tags each statement with its top topics.
3. **Kinds.** Jev labels each section *current*, *history* or *plan*; only current guidance is compared. An
   owner's `checks/kinds.json` overrides a label by file or folder prefix.
4. **Pairs.** Statements that share a topic or close wording, from different sections.
5. **Judging.** Jev asks "do these contradict?" of every pair and "are they about the same specific thing?"
   of the top 2,000. A separate number check pairs statements that count the same noun with different
   numbers; Jev only judges whether they count the same thing, because Jev is weak at arithmetic.
6. **Review.** Claude reviews the top of both lists and records a verdict per pair; a false alarm stays
   silent until either statement changes.

The first run is the expensive one: a full review of the ranked lists. After it, `wiki accept` records the
reviewed statements, and every later `check` lists only pairs that touch a new or edited statement (delta
mode), typically a few pairs per edit. `--deep` brings the full ranking back.

## Enforcing code rules: `wiki lint`

For the rules a parser cannot check, such as *UI code never writes application state*. Mechanical rules (layering,
size limits) stay in the project's own tools.

Rules live in the project, in `docs/wiki/checks/lint.json`:

```json
{
  "id": "ui_never_writes_state",
  "paths": ["src/ui/"],
  "rule": "UI code never writes application state. It may read the store, but only actions change it. …",
  "exceptions": ["`App.bootstrap()` may seed the store: it runs once, before any UI exists. …"],
  "true": "The function assigns a store field or calls a mutating store method.",
  "false": "The function only reads the store and changes its own widgets.",
  "threshold": 0.5
}
```

Jev reads each function in the rule's paths (one request per function, one question per rule) and the
report lists every function above the threshold. Only GDScript is extracted today; a language is added
when a project needs one.

**Exceptions are data.** A rule's sanctioned exceptions are written down in the project's architecture doc
first, then listed under `exceptions`, where Jev reads them as part of the rule. A new exception is one line,
with no code change. A one-off false alarm is recorded as a verdict instead, and stays silent until that
function's code changes.

**Wording is measured, not guessed.** Jev reads rules literally, so most false alarms come from wording.
Before a reworded rule is trusted, plant violations into copies of real functions and score them next to
clean ones; a rule that cannot separate the two (for example *comments explain why, not what*) is dropped.

## The wiki itself

`wiki init` sets up `docs/wiki/` in a repo: conventions, a style
guide, seven maintenance protocols, a home page, an overview, a generated doc map and session logs. The
project's existing docs stay where they are and the wiki links into them. Selected pages are mirrored to
the public GitHub Wiki (see [Conventions](Conventions)).

## Related pages

- [Overview](Overview)
- [Measurements](Measurements)
- [Protocol 2: Spot-check](Protocol-2-Spot-Check)
- [Protocol 5: Session log](Protocol-5-Session-Log)
