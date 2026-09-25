# jevauto

Browser and Windows-app automation where **Claude plans**, **Jev (TypeSafe) checks every action before it runs**, and Playwright or Windows UI Automation executes.

```
task ─► Claude (claude-opus-5) proposes: act(action, element_id, intent, expect)
            │
            ▼
   observe screen ─► elements with stable ids + visible text (secrets masked)
            │
            ▼
   Jev, two parallel requests (~100 ms):
     target         Choice over elements + "none"     which element fits the intent?
     planner_match  Noul                              does Claude's pick do the job?
     risk           Choice observe/edit_local/commit  what does this action affect?
     blocker        Choice                            CAPTCHA, sign-in, dialog, error?
            │
            ▼
   policy.py (plain code): act · confirm with user · reject (reasons + top candidates back to Claude) · halt (hand to user)
            │
            ▼
   execute ─► re-observe ─► Jev Noul: is `expect` now true? ─► result back to Claude
```

Hard rules, applied in code no matter what the models say:
- Password fields and CAPTCHAs are handed to you.
- Anything that might be irreversible needs your `y`. That covers a Jev commit probability of 0.2 or more, or a button named submit/send/buy/delete and the like.
- Screen text is treated as data, not instructions.
- API-key and token-looking strings are masked before any screen content reaches Claude or Jev.

## Projected token savings

The coding harness cuts what a Claude session re-reads, not what it writes. Measured on one game project with
about 170k tokens of design docs:

- **Session start:** ~170k tokens of docs → a 15–25k reading list (~85–90% less).
- **Handover:** a ~55k-token conversation → a ~5.6k digest (~90% less).
- **Doc and code audits:** after the first full review, each re-check lists only what changed (~99% less).

Projected per session (one start plus one handover): about 65% less reading for a repo with 20k tokens of docs,
77% at 80k and 86% at 170k. The formula, worked examples and caveats are on the
[Projected token savings](https://github.com/silvariasereneblossom/jevauto/wiki/Token-Savings) wiki page.

## Setup

Linux and macOS:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/playwright install --with-deps chromium
source .venv/bin/activate   # puts `jevauto` on PATH
```

On Debian and Ubuntu, the system Python needs `sudo apt install python3-venv` first, and `python3-tk` if you want
the keys window. `--with-deps` installs Chromium's system libraries, so it asks for sudo.

Windows (PowerShell):

```powershell
python -m venv .venv; .venv\Scripts\pip install -e ".[dev]"; .venv\Scripts\playwright install chromium
.venv\Scripts\Activate.ps1
```

Browser automation and the whole coding harness (`jevauto ctx`, `jevauto wiki`) run on all three. Desktop-app
automation (`--window`, `--launch`, the `attach_window` tool) drives Windows UI Automation, so it is Windows-only.

### Jev provider

You need a key for one of these:
- **TypeSafe** (`TYPESAFE_API_KEY`): Jev's maker. This is the default whenever the key is stored, and the model is pinned to `jev-1.13.0`.
- **OpenJEV** (`OPENJEV_API_KEY`): a third-party public gateway to Jev ([openjev.sh](https://openjev.sh)), paid for by fees from its $JEV token. It's used when no TypeSafe key is stored. It only offers the model alias `openjev`, so the underlying Jev version can change without notice.

To force one, set `JEVAUTO_JEV_PROVIDER=typesafe` or `openjev`.

### API keys (no env-var editing)

`jevauto keys gui` opens a window for pasting keys. It lists the TypeSafe, OpenJEV and Anthropic keys, and "Add a key" stores a key for any other service under an env-var-style name. Every stored key is loaded into the environment of each jevauto run.

Keys go in the OS credential vault (Windows Credential Manager, the macOS Keychain, or GNOME Keyring / KWallet on
Linux) and are loaded automatically when a task runs:

```bash
jevauto keys set TYPESAFE_API_KEY --clipboard   # copy the key first; the clipboard is cleared afterwards
jevauto keys set ANTHROPIC_API_KEY              # or paste at a hidden prompt
jevauto keys list                               # masked
jevauto keys import-env                         # move keys that are already env vars into the vault
```

When looking up a key, the loader checks this process's environment first, then the vault; on Windows it also checks user environment variables saved in the registry, so a variable you set after opening the terminal still works.

No vault, as on a headless server or in CI? Skip the `keys` commands and export the variables instead (`export OPENJEV_API_KEY=...`); the environment always wins.

## Drive it from Claude Code (no Anthropic API key)

jevauto is also an MCP server, so Claude Code itself can plan the steps. Only `TYPESAFE_API_KEY` is needed:

```bash
claude mcp add jevauto --scope user -- <repo>/.venv/bin/python -m jevauto.mcp_server          # Linux, macOS
claude mcp add jevauto --scope user -- <repo>\.venv\Scripts\python.exe -m jevauto.mcp_server  # Windows
```

In a new session, ask Claude to do a task in the browser. The tools are `open_browser`, `attach_window`, `observe`, `navigate`, `act` and `close`. Every `act` passes the same Jev checks as the API planner. Actions that need your approval come back as NEEDS CONFIRMATION, and Claude asks you in chat before calling again with `confirmed=true`.

## Run with the built-in API planner

```bash
jevauto run "find the cheapest nonstop flight from Boston to Chicago next Friday" --url google.com/travel/flights
jevauto run "turn on dark mode" --window "^Settings$"                                            # Windows only
jevauto run "type a shopping list: eggs, milk" --launch notepad.exe --window "Untitled - Notepad"  # Windows only
```

Options:
- `--effort low|medium|high|xhigh|max`: planner effort.
- `--headless`, `--keep-open`, `--max-steps N`.
- `--jev-model`: pinned to `jev-1.13.0` by default, because the thresholds in `policy.py` assume it.

Desktop mode asks before attaching to a window, and it refuses a title pattern that matches more than one window. Windows 11 Notepad reopens your previous tabs in the same window, so point `--window` at the exact title you mean.

Every Jev question, answer and policy decision is appended to `runs/<timestamp>.jsonl`. Use these traces to tune the thresholds in `policy.py`: they're conservative starting points, not tuned values.

## Tests

```bash
.venv/bin/python -m pytest -q        # Windows: .venv\Scripts\python -m pytest -q
```

The tests run offline and need no keys. The real TypeSafe SDK talks to a mock transport. Browser tests use a local HTML fixture in headless Chromium. Desktop tests open a private WinForms window and never touch your own apps; they run on Windows only and are
skipped elsewhere. CI runs the suite on Ubuntu and Windows.

## Known limits (v1)

- Desktop-app automation is Windows-only (it uses Windows UI Automation).
- Elements inside iframes and shadow DOM aren't collected yet.
- Jev reads text only, so canvas-drawn UIs and custom-drawn desktop apps that don't expose UI Automation are invisible to it.
- Jev 1.13 is weak at arithmetic, dates and counting (see the TypeSafe "jaggedness" page). Keep those in the planner or in code, not in gate questions.

## Context harness (`jevauto ctx`)

Makes a fresh session cheap without losing context. Jev selects and labels; it never writes summaries.

```bash
jevauto ctx index <repo>                 # readable section index of the repo's Markdown docs
jevauto ctx find <repo> "<task>"         # Jev-picked reading list within a token budget (also the MCP tool context_find)
jevauto ctx digest <session|latest> --since 2026-09-20 --handover <repo>/docs/HANDOVER.md
```

On a game project with ~170k tokens of docs, `find` returns 12–25k tokens of sections, where reading every doc would cost ~168k.

## Living wiki (`jevauto wiki`)

Sets up `docs/wiki/` in a repo: conventions, style guide, seven protocols, a home page, an overview, a generated doc map and session logs.

```bash
jevauto wiki init <repo> --name "..." --summary "..." --check-cmd "..."
jevauto wiki map <repo>        # regenerate the doc map
jevauto wiki log <repo> latest --since <date>   # Protocol 5: session log from a Jev digest
jevauto wiki coverage <repo>   # Protocol 6: orphans and broken links
jevauto wiki check <repo>      # Protocol 2 extra: Jev-ranked claim pairs (experimental, see the protocol for measured limits)
```
