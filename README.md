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

## Setup

```bash
python -m venv .venv && .venv\Scripts\pip install -e ".[dev]" && .venv\Scripts\playwright install chromium
```

### Jev provider

You need a key for one of these:
- **TypeSafe** (`TYPESAFE_API_KEY`): Jev's maker. This is the default whenever the key is stored, and the model is pinned to `jev-1.13.0`.
- **OpenJEV** (`OPENJEV_API_KEY`): a third-party public gateway to Jev ([openjev.sh](https://openjev.sh)), paid for by fees from its $JEV token. It's used when no TypeSafe key is stored. It only offers the model alias `openjev`, so the underlying Jev version can change without notice.

To force one, set `JEVAUTO_JEV_PROVIDER=typesafe` or `openjev`.

### API keys (no env-var editing)

`jevauto keys gui` opens a window for pasting keys. It lists the TypeSafe, OpenJEV and Anthropic keys, and "Add a key" stores a key for any other service under an env-var-style name. Every stored key is loaded into the environment of each jevauto run.

Keys go in Windows Credential Manager and are loaded automatically when a task runs:

```bash
jevauto keys set TYPESAFE_API_KEY --clipboard   # copy the key first; the clipboard is cleared afterwards
jevauto keys set ANTHROPIC_API_KEY              # or paste at a hidden prompt
jevauto keys list                               # masked
jevauto keys import-env                         # move keys that are already env vars into the vault
```

When looking up a key, the loader checks three places in order: this process's environment, then the vault, then Windows user environment variables saved in the registry. The registry fallback means a variable you set after opening the terminal still works.

## Drive it from Claude Code (no Anthropic API key)

jevauto is also an MCP server, so Claude Code itself can plan the steps. Only `TYPESAFE_API_KEY` is needed:

```bash
claude mcp add jevauto --scope user -- <repo>\.venv\Scripts\python.exe -m jevauto.mcp_server
```

In a new session, ask Claude to do a task in the browser. The tools are `open_browser`, `attach_window`, `observe`, `navigate`, `act` and `close`. Every `act` passes the same Jev checks as the API planner. Actions that need your approval come back as NEEDS CONFIRMATION, and Claude asks you in chat before calling again with `confirmed=true`.

## Run with the built-in API planner

```bash
jevauto run "find the cheapest nonstop flight from Boston to Chicago next Friday" --url google.com/travel/flights
jevauto run "turn on dark mode" --window "^Settings$"
jevauto run "type a shopping list: eggs, milk" --launch notepad.exe --window "Untitled - Notepad"
```

Options:
- `--effort low|medium|high|xhigh|max`: planner effort.
- `--headless`, `--keep-open`, `--max-steps N`.
- `--jev-model`: pinned to `jev-1.13.0` by default, because the thresholds in `policy.py` assume it.

Desktop mode asks before attaching to a window, and it refuses a title pattern that matches more than one window. Windows 11 Notepad reopens your previous tabs in the same window, so point `--window` at the exact title you mean.

Every Jev question, answer and policy decision is appended to `runs/<timestamp>.jsonl`. Use these traces to tune the thresholds in `policy.py`: they're conservative starting points, not tuned values.

## Tests

```bash
.venv\Scripts\python -m pytest -q
```

The tests run offline and need no keys. The real TypeSafe SDK talks to a mock transport. Browser tests use a local HTML fixture in headless Chromium. Desktop tests open a private WinForms window and never touch your own apps.

## Known limits (v1)

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

Sets up `docs/wiki/` in a repo, after the IridescentCraft wiki template: conventions, style guide, seven protocols, a home page, an overview, a generated doc map and session logs.

```bash
jevauto wiki init <repo> --name "..." --summary "..." --check-cmd "..."
jevauto wiki map <repo>        # regenerate the doc map
jevauto wiki log <repo> latest --since <date>   # Protocol 5: session log from a Jev digest
jevauto wiki coverage <repo>   # Protocol 6: orphans and broken links
jevauto wiki check <repo>      # Protocol 2 extra: Jev-ranked claim pairs (experimental, see the protocol for measured limits)
```
