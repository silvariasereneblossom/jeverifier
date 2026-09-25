# JeVerifier

A coding harness that puts **Jev** (TypeSafe's fast classifier) under a Claude coding session so the session reads
less and checks more:

- **Reading lists** instead of reading every doc at session start.
- **Session digests** instead of carrying a whole conversation into the next session.
- **Doc contradiction checks** and **code rule checks** that, after one full review, only look at what changed.

Jev only selects, ranks and labels; it never writes summaries or code, so it can leave something out but cannot
invent anything. Claude reviews what Jev surfaces, and every review is recorded so it is not paid for twice.

## Projected token savings

JeVerifier cuts what a Claude session re-reads, not what it writes. Measured on one game project with about 170k
tokens of design docs:

- **Session start:** ~170k tokens of docs → a 15–25k reading list (~85–90% less).
- **Handover:** a ~55k-token conversation → a ~5.6k digest (~90% less).
- **Doc and code audits:** after the first full review, each re-check lists only what changed (~99% less).

Projected per session (one start plus one handover): about 65% less reading for a repo with 20k tokens of docs,
77% at 80k and 86% at 170k. The formula, worked examples and caveats are on the
[Projected token savings](https://github.com/silvariasereneblossom/jeverifier/wiki/Token-Savings) wiki page.

## Setup

Linux and macOS:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
source .venv/bin/activate   # puts `jeverifier` on PATH
```

On Debian and Ubuntu, the system Python needs `sudo apt install python3-venv` first, and `python3-tk` if you want
the keys window.

Windows (PowerShell):

```powershell
python -m venv .venv; .venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\Activate.ps1
```

### Jev provider

You need a key for one of these:
- **TypeSafe** (`TYPESAFE_API_KEY`): Jev's maker. This is the default whenever the key is stored, and the model is pinned to `jev-1.13.0`.
- **OpenJEV** (`OPENJEV_API_KEY`): a third-party public gateway to Jev ([openjev.sh](https://openjev.sh)), paid for by fees from its $JEV token. It's used when no TypeSafe key is stored. It only offers the model alias `openjev`, so the underlying Jev version can change without notice.

To force one, set `JEVERIFIER_JEV_PROVIDER=typesafe` or `openjev`.

### API keys (no env-var editing)

`jeverifier keys gui` opens a window for pasting keys; "Add a key" stores a key for any other service under an
env-var-style name. Keys go in the OS credential vault (Windows Credential Manager, the macOS Keychain, or GNOME
Keyring / KWallet on Linux) and are loaded into the environment of every jeverifier run:

```bash
jeverifier keys set OPENJEV_API_KEY --clipboard   # copy the key first; the clipboard is cleared afterwards
jeverifier keys set TYPESAFE_API_KEY              # or paste at a hidden prompt
jeverifier keys list                              # masked
jeverifier keys import-env                        # move keys that are already env vars into the vault
```

The environment wins over the vault; on Windows, user environment variables saved in the registry are checked too,
so a variable set after the terminal opened still works. No vault, as on a headless server or in CI? Skip the
`keys` commands and export the variables instead (`export OPENJEV_API_KEY=...`).

### From Claude Code

Register the MCP server so a session can ask for a reading list itself (the `context_find` tool):

```bash
claude mcp add jeverifier --scope user -- <checkout>/.venv/bin/python -m jeverifier.mcp_server          # Linux, macOS
claude mcp add jeverifier --scope user -- <checkout>\.venv\Scripts\python.exe -m jeverifier.mcp_server  # Windows
```

## The workflow

**Session start: a reading list, not the whole docs.**

```bash
jeverifier ctx find <repo> "<task>"          # doc sections the task needs, within a token budget (default 25k)
jeverifier ctx index <repo>                  # every doc section with its size
```

**Handover: a digest, not the transcript.**

```bash
jeverifier ctx digest <session|latest> --since 2026-09-20 --handover <repo>/docs/HANDOVER.md
jeverifier wiki log <repo> latest --since <date>     # the digest as a dated session log in the repo's wiki
```

**Docs stay consistent.** One full review, then only what changed:

```bash
jeverifier wiki check <repo>                 # first run: Jev-ranked contradiction pairs; later runs: only pairs touching edits
jeverifier wiki verdict <repo> <id> false-alarm   # a false alarm stays silent until either statement changes
jeverifier wiki accept <repo>                # record the reviewed state; later checks are deltas (--deep for the full list)
jeverifier wiki selftest <repo>              # plant contradictions in a scratch copy and measure recall
```

**Code keeps its rules.** Rules a parser can't check live in `docs/wiki/checks/lint.json` with their documented
exceptions; unchanged functions are answered from the cache:

```bash
jeverifier wiki lint <repo>
```

**The wiki itself:** `jeverifier wiki init <repo>` sets up `docs/wiki/` (conventions, style guide, seven maintenance
protocols, home page, overview, doc map, session logs); `wiki map` regenerates the doc map, `wiki coverage` finds
orphan pages and broken links, and `wiki publish` mirrors an allowlisted part of a private repo to a public one.

Paid runs stop before they would pass `--max-cost` (default $1). How each part works, and what it measured:
[How it works](https://github.com/silvariasereneblossom/jeverifier/wiki/How-It-Works),
[Measurements](https://github.com/silvariasereneblossom/jeverifier/wiki/Measurements).

## Tests

```bash
.venv/bin/python -m pytest -q        # Windows: .venv\Scripts\python -m pytest -q
```

The tests run offline and need no keys: the real TypeSafe SDK talks to a mock transport. CI runs them on Ubuntu
(Python 3.12 and 3.14) and Windows.

## Known limits

- Code rule checks extract GDScript functions only; other languages are added when a project needs them.
- Recall figures come from one project; run `jeverifier wiki selftest` on yours before relying on them.
- Jev 1.13 is weak at arithmetic, dates and counting (see the TypeSafe "jaggedness" page), so numbers are compared
  in code and Jev only judges whether two statements are about the same thing.
